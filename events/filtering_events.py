from dataclasses import dataclass
from typing import Any, List, Optional


# =========================================================
# 1. ENQUEUE / BACKPRESSURE
# =========================================================

@dataclass
class FilteringEnqueuedEvent:
    correlation_id: str
    node_id: str
    queue_size: int


# =========================================================
# 2. WORKER LIFECYCLE
# =========================================================

@dataclass
class FilteringWorkerCycleStartedEvent:
    worker_id: int
    correlation_id: str
    node_id: str


# =========================================================
# 3. INPUT OBSERVABILITY
# =========================================================

@dataclass
class FilteringInputSnapshotEvent:
    correlation_id: str
    raw_links_count: int
    raw_items_count: int


# =========================================================
# 4. LINK FILTERING TRACE
# =========================================================

@dataclass
class LinkFilteringCompletedEvent:
    correlation_id: str
    accepted: List[str]
    rejected_count: int


# =========================================================
# 5. ITEM FILTERING TRACE
# =========================================================

@dataclass
class ItemFilteringCompletedEvent:
    correlation_id: str
    accepted: List[Any]          # (item, hash)
    rejected_count: int


# =========================================================
# 6. OUTPUT EVENT (MAIN RESULT)
# =========================================================

@dataclass
class ContentFilteredEvent:
    correlation_id: str
    node: Any

    links: List[str]
    items: List[Any]

    accepted_links_count: int
    rejected_links_count: int

    accepted_items_count: int
    rejected_items_count: int


# =========================================================
# 7. ERROR / FAILURE (FULL CONTEXT)
# =========================================================

@dataclass
class FilteringPipelineErrorEvent:
    correlation_id: Optional[str]
    node: Any

    stage: str  # WORKER | LINK_FILTER | ITEM_FILTER | EMISSION

    error_type: str
    error_message: str