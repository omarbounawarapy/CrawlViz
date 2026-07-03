from dataclasses import dataclass
from typing import Any, List, Tuple, Optional


# =========================================================
# 1. ENQUEUE / BACKPRESSURE
# =========================================================

@dataclass
class TransformationEnqueuedEvent:
    correlation_id: str
    node_id: str
    queue_size: int


# =========================================================
# 2. INPUT SNAPSHOT
# =========================================================

@dataclass
class TransformationInputSnapshotEvent:
    correlation_id: str
    node_id: str
    ready_state: bool
    items_count: int


# =========================================================
# 3. EXECUTION START
# =========================================================

@dataclass
class TransformationStartedEvent:
    worker_id: Optional[int]
    correlation_id: str
    node_id: str
    items_count: int


# =========================================================
# 4. SUCCESS COMPLETION
# =========================================================

@dataclass
class TransformationCompletedEvent:
    correlation_id: str
    node: Any
    links : Any
    transformed_items: List[Tuple[Any, str]]
    output_count: int


# =========================================================
# 5. FAILURE EVENT (DEBUG CONTEXT)
# =========================================================

@dataclass
class TransformationFailedEvent:
    correlation_id: str
    node: Any


    error_type: str
    error_message: str





# =========================================================
# 6. DOWNSTREAM EVENT (PIPELINE OUTPUT)
# =========================================================

@dataclass
class ItemsTransformedEvent:
    correlation_id: str
    node: Any

    transformed_items: List[Tuple[Any, str]]