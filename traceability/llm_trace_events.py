from dataclasses import dataclass
from typing import Dict, List, Optional


# =========================================================
# LLM HANDLER TRACE EVENTS
# =========================================================

@dataclass
class LLM_PromptBuilt:
    trace_id: str
    node_id: str
    request_id: str
    llm_type: str
    model: str
    strategy: str               # context class name
    prompt_len: int
    prompt_preview: str         # first 400 chars


@dataclass
class LLM_RequestDispatched:
    trace_id: str
    node_id: str
    request_id: str
    llm_type: str
    model: str


@dataclass
class LLM_ResponseReceived:
    trace_id: str
    node_id: str
    request_id: str
    latency_ms: float
    status_ok: bool
    raw_preview: str            # first 300 chars of raw response


@dataclass
class LLM_ResponseParsed:
    trace_id: str
    node_id: str
    request_id: str
    output_keys: List[str]
    token_usage: Optional[Dict[str, int]]
    output_preview: str         # first 300 chars of normalized result


@dataclass
class LLM_RequestFailed:
    trace_id: str
    node_id: str
    request_id: str
    stage: str                  # "dispatch" | "translate_request" | "translate_response"
    error_type: str
    error_message: str
    retry_attempt: int = 0