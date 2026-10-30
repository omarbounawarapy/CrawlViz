"""Typed LLM layer, built beside `infrastructure/llm_handler.py`.

No caller uses it yet: callers move to it one at a time, and the old handler
goes last. Other areas import from here only (ARCH-2).
"""

from .json_output import (
    LlmOutputError,
    RepairCall,
    ValidatedOutput,
    parse_and_validate,
    parse_llm_json,
    validate_llm_output,
)
from .types import (
    LLM_CALL_RECORD_SCHEMA_VERSION,
    CallOutcome,
    ChatRole,
    LlmCallError,
    LlmCallRecord,
    LlmClient,
    LlmMessage,
    LlmRequest,
    LlmResponse,
    TokenUsage,
    render_messages,
)

__all__ = [
    "LLM_CALL_RECORD_SCHEMA_VERSION",
    "CallOutcome",
    "ChatRole",
    "LlmCallError",
    "LlmCallRecord",
    "LlmClient",
    "LlmMessage",
    "LlmOutputError",
    "LlmRequest",
    "LlmResponse",
    "RepairCall",
    "TokenUsage",
    "ValidatedOutput",
    "parse_and_validate",
    "parse_llm_json",
    "render_messages",
    "validate_llm_output",
]
