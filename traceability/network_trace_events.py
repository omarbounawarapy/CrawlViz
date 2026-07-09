from dataclasses import dataclass
from typing import Literal

# =========================================================
# NETWORK CLIENT TRACE EVENTS
# =========================================================

@dataclass
class NET_RequestCreated:
    trace_id: str
    node_id: str
    request_id: str
    method: str
    url: str
    has_auth_header: bool        # boolean only -- never log key values


@dataclass
class NET_RequestDispatched:
    trace_id: str
    node_id: str
    request_id: str
    strategy_class: Literal["GetRequestStrategy", "PostRequestStrategy"]


@dataclass
class NET_ResponseReceived:
    trace_id: str
    node_id: str
    request_id: str
    status_code: int
    response_size_bytes: int
    latency_ms: float


@dataclass
class NET_RequestFailed:
    trace_id: str
    node_id: str
    request_id: str
    error_type: Literal["timeout", "connection", "http_error", "unknown"]
    error_message: str
    status_code: int | None


@dataclass
class NET_RetryAttempted:
    trace_id: str
    node_id: str
    request_id: str
    attempt: int
    reason: str
