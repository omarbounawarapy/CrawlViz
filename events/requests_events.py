from dataclasses import dataclass
from typing import Any


# =========================================================
# 1. ENQUEUE / BACKPRESSURE
# =========================================================

@dataclass
class RequestEnqueuedEvent:
    correlation_id: str
    node_id: str
    queue_size: int


# =========================================================
# 2. REQUEST START
# =========================================================

@dataclass
class RequestStartedEvent:
    worker_id: int
    correlation_id: str
    node_id: str
    url: str


# =========================================================
# 3. RESPONSE METADATA (NETWORK OBSERVABILITY)
# =========================================================

@dataclass
class RequestResponseReceivedEvent:
    correlation_id: str
    node_id: str
    response_size: int


# =========================================================
# 4. SUCCESS OUTPUT (DOWNSTREAM INPUT)
# =========================================================

@dataclass
class PageFetchedEvent:
    correlation_id: str
    node: Any
    content: Any


# =========================================================
# 5. FAILURE EVENT (STRICT DEBUG CONTEXT)
# =========================================================

@dataclass
class RequestFailedEvent:
    correlation_id: str
    node: Any

    error_type: str
    error_message: str


# =========================================================
# 6. OPTIONAL (HIGH VALUE FOR PERFORMANCE ANALYSIS)
# =========================================================

@dataclass
class RequestTimingEvent:
    """
    Optional event for latency analysis (GUI charts, SLA tracking).
    """
    correlation_id: str
    node_id: str

    url: str
    duration_ms: float