import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, ClassVar, Protocol

import aiohttp
from aiohttp import hdrs

from crawlviz.shared import NetworkClient

from .anthropic_translator import AnthropicTranslator
from .call_log import CallTiming, LlmCallLog, PromptContext, call_error, legacy_request
from .endpoints import default_llm_endpoints
from .gemini_translator import GeminiTranslator
from .groq_translator import GroqTranslator
from .key_manager import KeyManager
from .nvidia_translator import NvidiaTranslator
from .open_router_translator import OpenRouterTranslator
from .openai_translator import OpenAITranslator
from .provider_statuses import REJECTED_KEY_STATUSES, SERVER_ERROR_STATUSES, TOO_MANY_REQUESTS
from .types import LlmTimeoutError, TokenUsage

logger = logging.getLogger(__name__)

# Longest wait for one HTTP attempt; reasoning models can take tens of seconds.
DEFAULT_TIMEOUT_SECONDS = 60.0
MILLISECONDS_PER_SECOND = 1000


@dataclass(frozen=True)
class RetryPolicy:
    """How LlmHandler retries a provider's transient failures: 429 and any 5xx.

    Attributes:
        max_retries: Retries after the first attempt; 0 turns retrying off.
        base_delay_seconds: Wait before the first retry when the provider
            sends no usable Retry-After.
        backoff_factor: Each further retry without Retry-After waits this
            many times longer.
        max_delay_seconds: No wait is longer. A Retry-After above it is not
            shortened: the error is raised at once, as the provider asked
            for more time than a scoring worker should block for.
        sleep: Waits between retries; tests pass a recorder.
    """

    max_retries: int = 3
    base_delay_seconds: float = 1.0
    backoff_factor: float = 2.0
    max_delay_seconds: float = 30.0
    sleep: Callable[[float], Awaitable[None]] = field(
        default=asyncio.sleep, compare=False, repr=False
    )

    def __post_init__(self) -> None:
        if self.max_retries < 0 or self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError(f"retry counts and delays must not be negative: {self}")
        if self.backoff_factor < 1:
            raise ValueError(f"backoff_factor must be at least 1: {self}")

    def backoff(self, retry: int) -> float:
        """Wait before retry number `retry` (0-based) without Retry-After."""
        delay = self.base_delay_seconds * self.backoff_factor**retry
        return min(delay, self.max_delay_seconds)


def parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    """Seconds to wait from a Retry-After header, or None if absent or unreadable.

    RFC 9110 allows delay-seconds or an HTTP-date; providers also send
    fractional seconds, which are accepted. A date in the past means now.
    """
    if value is None or not value.strip():
        return None
    try:
        seconds = float(value)
    except ValueError:
        return _seconds_until(value, now or datetime.now(UTC))
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def _seconds_until(http_date: str, now: datetime) -> float | None:
    try:
        when = parsedate_to_datetime(http_date)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:  # "-0000" zone: RFC 5322 says the time is UTC
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - now).total_seconds())


class RequestSender(Protocol):
    """Sends one HTTP request described by a translator's params dict."""

    async def emit_request(self, params: dict[str, Any]) -> Any: ...  # Any: provider JSON


def is_transient(status: int) -> bool:
    """True for answers worth retrying unchanged: rate limited or server error."""
    return status == TOO_MANY_REQUESTS or status in SERVER_ERROR_STATUSES


def retry_delay(
    policy: RetryPolicy, error: aiohttp.ClientResponseError, retries: int, call: str
) -> float | None:
    """Seconds to wait before retrying `error` under `policy`, or None to raise it.

    `retries` counts the retries already made. `call` names the provider and
    model for the log. Only they, the status and the wait are logged: never
    the key, URL, headers or body.
    """
    if not is_transient(error.status):
        return None
    if retries >= policy.max_retries:
        if policy.max_retries:
            logger.warning(
                "LLM %s answered HTTP %d; giving up after %d retries",
                call,
                error.status,
                retries,
            )
        return None
    header = error.headers.get(hdrs.RETRY_AFTER) if error.headers else None
    retry_after = parse_retry_after(header)
    if retry_after is not None and retry_after > policy.max_delay_seconds:
        logger.warning(
            "LLM %s answered HTTP %d asking to wait %.0f s, over the %.0f s limit; giving up",
            call,
            error.status,
            retry_after,
            policy.max_delay_seconds,
        )
        return None
    delay = policy.backoff(retries) if retry_after is None else retry_after
    logger.warning(
        "LLM %s answered HTTP %d; retry %d of %d in %.1f s (%s)",
        call,
        error.status,
        retries + 1,
        policy.max_retries,
        delay,
        "backoff" if retry_after is None else "Retry-After",
    )
    return delay


class HandlerContext(PromptContext, Protocol):
    """What the handler needs from a legacy context (`models.LlmContext`)."""

    def set_key(self, key: str) -> None: ...


class LegacyTranslator(Protocol):
    """A provider translator class: request shape out, parsed JSON reply in."""

    @staticmethod
    def translate_request(context: Any) -> dict[str, Any]: ...  # Any: provider JSON

    @staticmethod
    def translate_response(response: Any) -> dict[str, Any]: ...  # Any: provider JSON


@dataclass
class _CallProgress:
    """One call as it goes: its name for logs, attempts so far, the tokens it used."""

    name: str
    attempts: int = 0
    usage: TokenUsage = field(default_factory=TokenUsage)
    started: float = field(default_factory=time.monotonic)

    def latency_ms(self) -> float:
        return (time.monotonic() - self.started) * MILLISECONDS_PER_SECOND

    def timing(self, started_at: datetime) -> CallTiming:
        return CallTiming(started_at, self.attempts, self.latency_ms())


class LlmHandler:
    """Routes LLM requests through the correct translator and network client.

    Translators are registered by scoring_type string -- this is the same
    string a blueprint sets as ``scoring.params.scoring_type`` (for link
    scoring) or ``expansion.llm_type`` (for topic expansion), and the same
    string used as the top-level key in ``keys.json`` to look up that
    provider's API key(s). To add a new LLM provider: implement a
    translator class with translate_request(context) and
    translate_response(response), then register it in the `translators`
    dict below.

    Args:
        key_manager: Supplies a rotating API key for the request's provider.
        client: Sends the HTTP request. Defaults to a plain NetworkClient.

    Attributes:
        retry_policy: How 429 and 5xx answers are retried. Set it on an
            instance to change it, e.g. ``RetryPolicy(max_retries=0)`` for a
            caller that runs its own retries. Each retry asks the KeyManager
            for a key again, so it moves to the next key when there are several.
        timeout_seconds: Longest wait for one HTTP attempt, a positive number.
            Set it on an instance to change it. An attempt that gets no answer
            in time ends the call with `LlmTimeoutError` and is not retried;
            the client's own timeout still applies when it is shorter.
        call_log: Records every call: tokens, cost, latency, attempts and
            outcome (`LlmCallLog`). None, the default, records nothing. A
            constructor argument, so a wrapper such as `TracedLlmHandler`
            cannot hide an assignment from the handler.
    """

    retry_policy: RetryPolicy = RetryPolicy()

    translators: ClassVar[dict[str, LegacyTranslator]] = {
        "openrouter": OpenRouterTranslator,
        "openai": OpenAITranslator,
        "anthropic": AnthropicTranslator,
        "gemini": GeminiTranslator,
        "nvidia": NvidiaTranslator,
        "groq": GroqTranslator,
    }

    def __init__(  # noqa: PLR0913 (optional collaborators and request options, each defaulted)
        self,
        key_manager: KeyManager,
        client: RequestSender | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        endpoints: dict[str, str] | None = None,
        *,
        call_log: LlmCallLog | None = None,
    ):
        self.call_log = call_log
        self.client: RequestSender = client or NetworkClient()
        self.timeout_seconds = DEFAULT_TIMEOUT_SECONDS
        self.key_manager = key_manager
        # Optional request parameters; None leaves the provider's default.
        self.max_tokens = max_tokens
        self.temperature = temperature
        # Only entries that differ from the built-in URL are applied.
        self.endpoints = {
            p: u for p, u in (endpoints or {}).items() if u and u != default_llm_endpoints().get(p)
        }

    @property
    def timeout_seconds(self) -> float:
        return self._timeout_seconds

    @timeout_seconds.setter
    def timeout_seconds(self, seconds: float) -> None:
        if not 0 < seconds < math.inf:
            raise ValueError(f"timeout_seconds must be a positive number, not {seconds}")
        self._timeout_seconds = seconds

    def _apply_options(self, llm_type: str, params: dict) -> None:
        """Set the configured max_tokens/temperature in the provider's own
        request shape (Gemini nests them under generationConfig)."""
        data = params.get("data")
        if not isinstance(data, dict):
            return
        if llm_type == "gemini":
            cfg = data.setdefault("generationConfig", {})
            if self.max_tokens is not None:
                cfg["maxOutputTokens"] = self.max_tokens
            if self.temperature is not None:
                cfg["temperature"] = self.temperature
            return
        if self.max_tokens is not None:
            data["max_tokens"] = self.max_tokens
        if self.temperature is not None:
            data["temperature"] = self.temperature

    def _apply_endpoint(self, llm_type: str, params: dict, context) -> None:
        endpoint = self.endpoints.get(llm_type)
        if not endpoint:
            return
        if llm_type == "gemini":
            endpoint = f"{endpoint.rstrip('/')}/{context.get_model_information()}:generateContent"
        params["url"] = endpoint

    async def send(self, context) -> dict:
        """Send one LLM request end to end: key, translate, dispatch, normalize.

        With a `call_log`, the call is recorded whether it is answered or fails.

        Raises:
            ValueError: If `context`'s scoring type has no registered translator.
            aiohttp.ClientResponseError: If the provider still refuses after the
                key drops and the retries `retry_policy` allows.
            LlmTimeoutError: If an attempt got no answer within `timeout_seconds`
                or the client's own timeout. A timeout is not retried: the
                worker has already waited the whole timeout once.
        """
        llm_type = context.get_scoring_type()
        translator_cls = self.translators.get(llm_type)
        if translator_cls is None:
            raise ValueError(
                f"Unknown scoring type: {llm_type!r}. Registered: {list(self.translators.keys())}"
            )
        call = _CallProgress(f"{llm_type}/{context.get_model_information()}")
        if self.call_log is None:
            return await self._exchange(context, llm_type, translator_cls, call)
        return await self._send_logged(context, llm_type, translator_cls, call, self.call_log)

    async def _send_logged(
        self,
        context: HandlerContext,
        llm_type: str,
        translator_cls: LegacyTranslator,
        call: _CallProgress,
        call_log: LlmCallLog,
    ) -> dict[str, Any]:  # Any: the parsed reply, provider JSON
        """`_exchange`, then its record. A record that cannot be written never
        changes the call's result: an answer the provider was paid for is
        returned, and a failed call raises its own error with a note."""
        request = legacy_request(context, temperature=self.temperature, max_tokens=self.max_tokens)
        started_at = datetime.now(UTC)
        try:
            result = await self._exchange(context, llm_type, translator_cls, call)
        except Exception as error:
            failure = call_error(error, call.name, call.timing(started_at))
            try:
                await call_log.call_failed(request, failure, started_at)
            except OSError as write_error:
                error.add_note(f"Its call record could not be written: {write_error}")
            raise
        try:
            await call_log.call_answered(request, result, call.usage, call.timing(started_at))
        except OSError as write_error:
            logger.warning(
                "%s: the answer is kept, but its call record could not be written: %s",
                call.name,
                write_error,
            )
        return result

    async def _exchange(
        self,
        context: HandlerContext,
        llm_type: str,
        translator_cls: LegacyTranslator,
        call: _CallProgress,
    ) -> dict[str, Any]:  # Any: the parsed reply, provider JSON
        """The attempts of one call, retries included; `call` counts them."""
        retries = 0
        while True:
            key = await self.key_manager.next_key(llm_type)
            context.set_key(key)
            params = translator_cls.translate_request(context)
            self._apply_endpoint(llm_type, params, context)
            self._apply_options(llm_type, params)
            call.attempts += 1
            try:
                response = await self._dispatch(params, call.name)
                break
            except TimeoutError as e:
                logger.warning("%s; the call is given up at attempt %d", e, call.attempts)
                raise LlmTimeoutError(
                    str(e), attempts=call.attempts, latency_ms=call.latency_ms()
                ) from e
            except aiohttp.ClientResponseError as e:
                # A rejected key (401/403) will never start working: drop it
                # from rotation and retry with the next one, if any is left.
                is_rejected_key = e.status in REJECTED_KEY_STATUSES
                if is_rejected_key and await self.key_manager.mark_invalid(llm_type, key):
                    continue
                delay = retry_delay(self.retry_policy, e, retries, call.name)
                if delay is None:
                    raise
                retries += 1
                await self.retry_policy.sleep(delay)
        usage = getattr(translator_cls, "translate_usage", None)
        if usage is not None:
            input_tokens, output_tokens = usage(response)
            call.usage = TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)
            if hasattr(context, "set_usage"):
                context.set_usage(call.usage.input_tokens, call.usage.output_tokens)
        return translator_cls.translate_response(response)

    async def _dispatch(self, params: dict, call: str) -> object:
        """One HTTP attempt, abandoned after `timeout_seconds`.

        Raises:
            TimeoutError: If no answer came in time. The message names the
                provider and model (`call`) and which timeout fired, never the
                key or URL, so it is safe to log and record.
        """
        deadline = asyncio.timeout(self.timeout_seconds)
        try:
            async with deadline:
                return await self.client.emit_request(params)
        except TimeoutError as e:
            if deadline.expired():
                reason = f"gave no answer within {self.timeout_seconds:g} s"
            else:  # the network client's own, shorter timeout
                reason = "timed out in the network client"
            raise TimeoutError(f"LLM {call} {reason}") from e
