from dataclasses import dataclass
from typing import Any, List, Dict


# =========================================================
# 1. INPUT / INGESTION TRACE
# =========================================================

@dataclass
class PriorityInputSnapshotEvent:
    correlation_id: str
    node_id: str
    scored_links_count: int


# =========================================================
# 2. EXECUTION START
# =========================================================

@dataclass
class PriorityCalculationStartedEvent:
    worker_id: int
    correlation_id: str
    node_id: str
    input_links_count: int


# =========================================================
# 3. SUCCESS OUTPUT
# =========================================================

@dataclass
class PriorityCalculatedEvent:
    correlation_id: str
    parent: Any  # Node

    links: List[Dict[str, Any]]  # {link, score, priority}
    output_count: int


# =========================================================
# 4. FAILURE TRACE (STRICT DEBUG CONTEXT)
# =========================================================

@dataclass
class PriorityCalculationFailedEvent:
    correlation_id: str
    node: Any  # Node

    stage: str  # "PRIORITY_COMPUTATION"

    error_type: str
    error_message: str

    input_links_count: int


# =========================================================
# 5. OPTIONAL (RECOMMENDED FOR FUTURE GUI ENHANCEMENT)
# =========================================================

@dataclass
class PriorityLinkTransformationEvent:
    """
    Optional fine-grained observability event.
    Only enable if you want step-by-step animation in GUI.
    """
    correlation_id: str
    node_id: str

    link: str
    score: float
    computed_priority: float