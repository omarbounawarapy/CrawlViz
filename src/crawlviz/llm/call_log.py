"""Call records for `LlmHandler`, the handler the crawl uses until callers move to `LlmClient`.

The handler takes a context object (`models.LlmContext`), not an `LlmRequest`. Every
translator sends the context's prompt as one user message, so the request built here
renders and hashes the same as a typed request with that message (``prompt_registry``),
and records from both handlers read alike.

The legacy translators return the parsed JSON object, not the model's text, so
``raw_reply`` holds that object as JSON. An empty object is how they say the reply could
not be read, and is recorded as ``invalid_output``.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol

import aiohttp

from crawlviz.shared import get_trace

from .call_recorder import LlmCallRecorder
from .prompt_registry import hash_messages
from .types import (
    CallOutcome,
    ChatRole,
    LlmCallError,
    LlmCallRecord,
    LlmMessage,
    LlmRequest,
    LlmResponse,
    TokenUsage,
)

# Stands in for a context that names no model, so the record still validates.
UNKNOWN_MODEL: Final = "unknown"


class PromptContext(Protocol):
    """What the handler reads from a legacy context to describe the call."""

    def get_scoring_type(self) -> str: ...
    def get_model_information(self) -> str: ...
    def get_prompt(self) -> str: ...


@dataclass(frozen=True)
class CallTiming:
    """When a call started and what it took, as the handler measured it."""

    started_at: datetime
    attempts: int
    latency_ms: float


def legacy_request(
    context: PromptContext, *, temperature: float | None, max_tokens: int | None
) -> LlmRequest:
    """The typed request the handler sends for `context`, for its record only."""
    messages = (LlmMessage(role=ChatRole.USER, content=context.get_prompt()),)
    trace_id, node_id = get_trace()
    return LlmRequest(
        provider=context.get_scoring_type(),
        model=context.get_model_information() or UNKNOWN_MODEL,
        messages=messages,
        prompt_hash=hash_messages(messages),
        temperature=temperature,
        max_tokens=max_tokens,
        node_id=node_id or None,
        trace_id=trace_id or None,
    )


def call_error(error: Exception, call: str, timing: CallTiming) -> LlmCallError:
    """`error` as a typed call error. Its message names only `call` (provider and model)
    and the status or the error class, never the key or URL (SEC-3)."""
    if isinstance(error, LlmCallError):
        return error
    outcome, status = CallOutcome.BAD_RESPONSE, None
    message = f"LLM {call} sent an answer that could not be read ({type(error).__name__})"
    if isinstance(error, aiohttp.ClientResponseError):
        outcome, status = CallOutcome.HTTP_ERROR, error.status
        message = f"LLM {call} answered HTTP {error.status}"
    elif isinstance(error, aiohttp.ClientError | OSError):
        outcome = CallOutcome.NETWORK_ERROR
        message = f"LLM {call} could not be reached ({type(error).__name__})"
    return LlmCallError(
        message,
        outcome=outcome,
        attempts=timing.attempts,
        latency_ms=timing.latency_ms,
        status=status,
    )


@dataclass(frozen=True)
class LlmCallLog:
    """Where `LlmHandler` sends the record of each call it makes.

    Attributes:
        recorder: Prices, counts and stores each record.
    """

    recorder: LlmCallRecorder

    async def call_answered(
        self,
        request: LlmRequest,
        result: dict[str, Any],  # Any: the parsed reply, provider JSON
        usage: TokenUsage,
        timing: CallTiming,
    ) -> LlmCallRecord:
        """Record a call the provider answered; returns the record as stored."""
        response = LlmResponse(
            text=json.dumps(result, ensure_ascii=False),
            model=request.model,
            usage=usage,
            attempts=timing.attempts,
            latency_ms=timing.latency_ms,
        )
        outcome = CallOutcome.OK if result else CallOutcome.INVALID_OUTPUT
        record = LlmCallRecord.from_response(
            request, response, started_at=timing.started_at, outcome=outcome
        )
        return await self.recorder.record(record)

    async def call_failed(
        self, request: LlmRequest, error: LlmCallError, started_at: datetime
    ) -> LlmCallRecord:
        """Record a call that got no usable answer; returns the record as stored."""
        record = LlmCallRecord.from_error(request, error, started_at=started_at)
        return await self.recorder.record(record)
