"""Typed request, response and call record for every LLM call, and the client protocol.

`LlmClient` is what callers depend on; provider adapters, the cache and the
offline doubles implement it. `LlmCallRecord` is one line of `llm_calls.jsonl`
in the run folder (ADR 12), a stored format with a `schema_version` (ADR 5).
"""

from datetime import datetime
from enum import StrEnum
from typing import Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

LLM_CALL_RECORD_SCHEMA_VERSION: Final = 1


class ChatRole(StrEnum):
    """Who a message speaks for. Untrusted page text only ever goes in `USER`."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class CallOutcome(StrEnum):
    """How one call ended, as recorded and shown in the "Why" tab."""

    OK = "ok"
    REPAIRED = "repaired"  # the first reply failed validation, the repair answer passed
    INVALID_OUTPUT = "invalid_output"  # the reply never passed validation
    HTTP_ERROR = "http_error"  # the provider answered with an error status
    NETWORK_ERROR = "network_error"  # no answer: the connection was refused or reset
    TIMEOUT = "timeout"  # no answer within the request timeout
    BAD_RESPONSE = "bad_response"  # an answer that is not a chat completion


# Outcomes of a call that ended without a valid answer.
FAILED_OUTCOMES: Final = frozenset(
    {
        CallOutcome.INVALID_OUTPUT,
        CallOutcome.HTTP_ERROR,
        CallOutcome.NETWORK_ERROR,
        CallOutcome.TIMEOUT,
        CallOutcome.BAD_RESPONSE,
    }
)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LlmMessage(_Frozen):
    role: ChatRole
    content: str


class TokenUsage(_Frozen):
    """Tokens one call used, as the provider reported them; 0 when it reported none."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class LlmRequest(_Frozen):
    """One chat completion to send, independent of the provider's wire shape.

    Attributes:
        provider: Provider key, the same string `keys.json` and the blueprint use.
        model: Model id sent to the provider.
        messages: The conversation, system message first if there is one.
        prompt_id: Id of the `prompts/<id>.md` file the messages were rendered from.
        prompt_hash: sha256 of the rendered messages (see `prompt_registry`).
        temperature: None leaves the provider's default.
        max_tokens: None leaves the provider's default.
        json_output: Ask for a JSON object where the provider supports it.
        crawl_id, node_id, trace_id: Log and record context (OBS-1).
    """

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    messages: tuple[LlmMessage, ...] = Field(min_length=1)
    prompt_id: str | None = None
    prompt_hash: str | None = None
    temperature: float | None = Field(default=None, ge=0)
    max_tokens: int | None = Field(default=None, gt=0)
    json_output: bool = False
    crawl_id: str | None = None
    node_id: str | None = None
    trace_id: str | None = None


class LlmResponse(_Frozen):
    """The provider's answer and what it took to get it.

    Attributes:
        text: The reply as the model wrote it, unparsed.
        model: Model id the provider says answered; the requested one if it did not say.
        usage: Tokens in and out.
        attempts: HTTP attempts made, retries included; 0 for a cache hit.
        latency_ms: Wall time from the first attempt to the answer, waits included.
        cache_hit: True when the answer came from a cache, not the provider.
        finish_reason: Why the model stopped, when the provider says.
    """

    text: str
    model: str
    usage: TokenUsage = TokenUsage()
    attempts: int = Field(ge=0)
    latency_ms: float = Field(ge=0)
    cache_hit: bool = False
    finish_reason: str | None = None


class LlmCallError(Exception):
    """A call that produced no usable answer, with what it cost to find out.

    The message names the provider, model and status only: never the key, the
    URL, headers or body (SEC-3), so it is safe to log and to record.
    """

    def __init__(
        self,
        message: str,
        *,
        outcome: CallOutcome,
        attempts: int,
        latency_ms: float,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.outcome = outcome
        self.attempts = attempts
        self.latency_ms = latency_ms
        self.status = status


class LlmTimeoutError(LlmCallError, TimeoutError):
    """A call given up because no answer came within the request timeout.

    It is also a `TimeoutError`, so code that already catches that keeps working.
    """

    def __init__(self, message: str, *, attempts: int, latency_ms: float) -> None:
        super().__init__(
            message, outcome=CallOutcome.TIMEOUT, attempts=attempts, latency_ms=latency_ms
        )


class LlmClient(Protocol):
    """Sends one request and returns the answer, or raises `LlmCallError`."""

    async def complete(self, request: LlmRequest) -> LlmResponse: ...


class LlmCallRecord(_Frozen):
    """One LLM call as stored in `llm_calls.jsonl` (LLM-3).

    `rendered_prompt` and `raw_reply` hold page text and are kept only when the
    recorder is told to store them. Keys never appear here (SEC-3).
    """

    schema_version: Literal[1] = LLM_CALL_RECORD_SCHEMA_VERSION
    started_at: datetime
    provider: str
    model: str
    prompt_id: str | None = None
    prompt_hash: str | None = None
    temperature: float | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    latency_ms: float = Field(ge=0)
    attempts: int = Field(ge=0)
    cache_hit: bool = False
    outcome: CallOutcome
    error: str | None = None
    crawl_id: str | None = None
    node_id: str | None = None
    trace_id: str | None = None
    rendered_prompt: str | None = None
    raw_reply: str | None = None

    @classmethod
    def from_response(
        cls,
        request: LlmRequest,
        response: LlmResponse,
        *,
        started_at: datetime,
        outcome: CallOutcome = CallOutcome.OK,
        cost_usd: float | None = None,
    ) -> "LlmCallRecord":
        """The record of a call that got an answer (valid or not, per `outcome`)."""
        return cls.model_validate(
            {
                **_request_fields(request),
                "started_at": started_at,
                "model": response.model,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cost_usd": cost_usd,
                "latency_ms": response.latency_ms,
                "attempts": response.attempts,
                "cache_hit": response.cache_hit,
                "outcome": outcome,
                "raw_reply": response.text,
            }
        )

    @classmethod
    def from_error(
        cls, request: LlmRequest, error: LlmCallError, *, started_at: datetime
    ) -> "LlmCallRecord":
        """The record of a call that got no usable answer."""
        return cls.model_validate(
            {
                **_request_fields(request),
                "started_at": started_at,
                "model": request.model,
                "latency_ms": error.latency_ms,
                "attempts": error.attempts,
                "outcome": error.outcome,
                "error": str(error),
            }
        )


def render_messages(messages: tuple[LlmMessage, ...]) -> str:
    """The conversation as one readable text, as the "Why" tab shows it."""
    return "\n\n".join(f"[{message.role}]\n{message.content}" for message in messages)


def _request_fields(request: LlmRequest) -> dict[str, object]:
    return {
        "provider": request.provider,
        "prompt_id": request.prompt_id,
        "prompt_hash": request.prompt_hash,
        "temperature": request.temperature,
        "crawl_id": request.crawl_id,
        "node_id": request.node_id,
        "trace_id": request.trace_id,
        "rendered_prompt": render_messages(request.messages),
    }
