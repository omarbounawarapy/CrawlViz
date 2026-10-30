import asyncio
import logging
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import aiohttp
from aiohttp import hdrs

from config import LLM_DEFAULT_ENDPOINTS

from .anthropic_translator import AnthropicTranslator
from .gemini_translator import GeminiTranslator
from .groq_translator import GroqTranslator
from .key_manager import KeyManager
from .network_client import NetworkClient
from .nvidia_translator import NvidiaTranslator
from .open_router_translator import OpenRouterTranslator
from .openai_translator import OpenAITranslator

logger = logging.getLogger(__name__)

TOO_MANY_REQUESTS = 429
SERVER_ERROR_STATUSES = range(500, 600)
REJECTED_KEY_STATUSES = (401, 403)


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
        client: Network client used to actually send the request. Defaults
            to a plain NetworkClient.

    Attributes:
        retry_policy: How 429 and 5xx answers are retried. Set it on an
            instance to change it, e.g. ``RetryPolicy(max_retries=0)`` for a
            caller that runs its own retries. Each retry asks the KeyManager
            for a key again, so it moves to the next key when there are several.
    """

    retry_policy: RetryPolicy = RetryPolicy()

    translators = {
        "openrouter": OpenRouterTranslator,
        "openai": OpenAITranslator,
        "anthropic": AnthropicTranslator,
        "gemini": GeminiTranslator,
        "nvidia": NvidiaTranslator,
        "groq": GroqTranslator,
    }

    def __init__(
        self,
        key_manager: KeyManager,
        client: NetworkClient | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        endpoints: dict[str, str] | None = None,
    ):
        self.client = client or NetworkClient()
        self.key_manager = key_manager
        # Optional request parameters; None leaves the provider's default.
        self.max_tokens = max_tokens
        self.temperature = temperature
        # Only entries that differ from the built-in URL are applied.
        self.endpoints = {
            p: u for p, u in (endpoints or {}).items() if u and u != LLM_DEFAULT_ENDPOINTS.get(p)
        }

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

        Raises:
            ValueError: If `context`'s scoring type has no registered translator.
            aiohttp.ClientResponseError: If the provider still refuses after the
                key drops and the retries `retry_policy` allows.
        """
        llm_type = context.get_scoring_type()

        translator_cls = self.translators.get(llm_type)
        if translator_cls is None:
            raise ValueError(
                f"Unknown scoring type: {llm_type!r}. Registered: {list(self.translators.keys())}"
            )

        retries = 0
        while True:
            key = await self.key_manager.next_key(llm_type)
            context.set_key(key)
            params = translator_cls.translate_request(context)
            self._apply_endpoint(llm_type, params, context)
            self._apply_options(llm_type, params)
            try:
                response = await self.client.emit_request(params)
                break
            except aiohttp.ClientResponseError as e:
                # A rejected key (401/403) will never start working: drop it
                # from rotation and retry with the next one, if any is left.
                is_rejected_key = e.status in REJECTED_KEY_STATUSES
                if is_rejected_key and await self.key_manager.mark_invalid(llm_type, key):
                    continue
                call = f"{llm_type}/{context.get_model_information()}"
                delay = retry_delay(self.retry_policy, e, retries, call)
                if delay is None:
                    raise
                retries += 1
                await self.retry_policy.sleep(delay)
        usage = getattr(translator_cls, "translate_usage", None)
        if usage is not None and hasattr(context, "set_usage"):
            context.set_usage(*usage(response))
        return translator_cls.translate_response(response)
