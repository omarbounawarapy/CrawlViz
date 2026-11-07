"""The LLM domain: provider handler and translators, keys, endpoints, the typed layer, call budget
and the LLM entry on the status board.

The typed layer has no caller yet: callers move to it one at a time, and `LlmHandler` goes last.
Other areas import from here only (ARCH-2).
"""

from .anthropic_translator import AnthropicTranslator
from .call_budget import CallBudget
from .call_recorder import LLM_CALLS_FILE_NAME, LlmCallRecorder, LlmCallTotals
from .cost_table import CostTable, ModelPrice, load_cost_table
from .endpoints import default_llm_endpoints
from .gemini_translator import GeminiTranslator
from .groq_translator import GroqTranslator
from .json_output import (
    LlmOutputError,
    RepairCall,
    ValidatedOutput,
    parse_and_validate,
    parse_llm_json,
    validate_llm_output,
)
from .key_manager import KeyManager
from .llm_handler import LlmHandler, RetryPolicy
from .llm_status import LlmState, LlmStatusTracker, RecentCalls, llm_facts, llm_state
from .nvidia_translator import NvidiaTranslator
from .open_router_translator import OpenRouterTranslator
from .openai_translator import OpenAITranslator
from .prompt_registry import PromptFileError, PromptRegistry, RenderedPrompt
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
    LlmTimeoutError,
    TokenUsage,
    render_messages,
)

__all__ = [
    "LLM_CALLS_FILE_NAME",
    "LLM_CALL_RECORD_SCHEMA_VERSION",
    "AnthropicTranslator",
    "CallBudget",
    "CallOutcome",
    "ChatRole",
    "CostTable",
    "GeminiTranslator",
    "GroqTranslator",
    "KeyManager",
    "LlmCallError",
    "LlmCallRecord",
    "LlmCallRecorder",
    "LlmCallTotals",
    "LlmClient",
    "LlmHandler",
    "LlmMessage",
    "LlmOutputError",
    "LlmRequest",
    "LlmResponse",
    "LlmState",
    "LlmStatusTracker",
    "LlmTimeoutError",
    "ModelPrice",
    "NvidiaTranslator",
    "OpenAITranslator",
    "OpenRouterTranslator",
    "PromptFileError",
    "PromptRegistry",
    "RecentCalls",
    "RenderedPrompt",
    "RepairCall",
    "RetryPolicy",
    "TokenUsage",
    "ValidatedOutput",
    "default_llm_endpoints",
    "llm_facts",
    "llm_state",
    "load_cost_table",
    "parse_and_validate",
    "parse_llm_json",
    "render_messages",
    "validate_llm_output",
]
