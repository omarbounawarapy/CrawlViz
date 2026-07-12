import time
import uuid
from typing import TYPE_CHECKING

from .llm_trace_events import (
    LLM_PromptBuilt,
    LLM_RequestDispatched,
    LLM_RequestFailed,
    LLM_ResponseParsed,
    LLM_ResponseReceived,
)
from .trace_context import get_trace

if TYPE_CHECKING:
    from infrastructure import LlmHandler

    from .emitter import TraceEmitter


class TracedLlmHandler:
    """Drop-in wrapper around LlmHandler that emits LLM_* trace events
    without modifying any translator or network logic.

    Example:
        traced_llm = TracedLlmHandler(LlmHandler(key_manager), tracer)
        # pass traced_llm wherever llm_handler is used
    """

    def __init__(self, inner: "LlmHandler", tracer: "TraceEmitter"):
        self._inner = inner
        self._tracer = tracer

    def __getattr__(self, name):
        # Proxy attribute access so downstream code that inspects the
        # handler directly (rather than through this wrapper) still works.
        return getattr(self._inner, name)

    async def send(self, context) -> dict:
        trace_id, node_id = get_trace()
        request_id = uuid.uuid4().hex[:10]
        t0 = time.monotonic()

        llm_type = context.get_scoring_type()
        model = context.get_model_information()
        prompt_str = context.get_prompt()

        await self._tracer.emit(LLM_PromptBuilt(
            trace_id=trace_id,
            node_id=node_id,
            request_id=request_id,
            llm_type=llm_type,
            model=model,
            strategy=type(context).__name__,
            prompt_len=len(prompt_str),
            prompt_preview=prompt_str[:400],
        ))

        await self._tracer.emit(LLM_RequestDispatched(
            trace_id=trace_id,
            node_id=node_id,
            request_id=request_id,
            llm_type=llm_type,
            model=model,
        ))

        try:
            result = await self._inner.send(context)
            latency_ms = (time.monotonic() - t0) * 1000

            await self._tracer.emit(LLM_ResponseReceived(
                trace_id=trace_id,
                node_id=node_id,
                request_id=request_id,
                latency_ms=latency_ms,
                status_ok=True,
                raw_preview=str(result)[:300],
            ))

            output_keys = list(result.keys()) if isinstance(result, dict) else []
            token_usage = result.get("usage") if isinstance(result, dict) else None
            await self._tracer.emit(LLM_ResponseParsed(
                trace_id=trace_id,
                node_id=node_id,
                request_id=request_id,
                output_keys=output_keys,
                token_usage=token_usage,
                output_preview=str(result)[:300],
            ))

            return result

        except Exception as exc:
            await self._tracer.emit(LLM_RequestFailed(
                trace_id=trace_id,
                node_id=node_id,
                request_id=request_id,
                stage="dispatch",
                error_type=type(exc).__name__,
                error_message=str(exc),
            ))
            raise
