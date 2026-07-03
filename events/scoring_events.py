from dataclasses import dataclass
from typing import Any, List


# =========================================================
# 1. ENQUEUE / BACKPRESSURE
# =========================================================

@dataclass
class ScoringEnqueuedEvent:
    correlation_id: str
    node_id: str
    queue_size: int


@dataclass 
class EmptyScoreResults:
    correlation_id: str
    node: Any
 


# =========================================================
# 2. INPUT READINESS SNAPSHOT
# =========================================================

@dataclass
class ScoringInputSnapshotEvent:
    correlation_id: str
    node_id: str
    ready_state: bool


# =========================================================
# 3. EXECUTION START
# =========================================================

@dataclass
class ScoringStartedEvent:
    worker_id: int
    correlation_id: str
    node_id: str


# =========================================================
# 4. SUCCESS INTERNAL COMPLETION
# =========================================================

@dataclass
class ScoringCompletedEvent:
    correlation_id: str
    node: Any

    scored_links: List[Any]
    output_count: int


# =========================================================
# 5. FAILURE EVENT (STRICT DEBUG CONTEXT)
# =========================================================

@dataclass
class ScoringFailedEvent:
    correlation_id: str
    node: Any

    stage: str  # "SCORING_SERVICE"

    error_type: str
    error_message: str


# =========================================================
# 6. DOWNSTREAM EVENT (PIPELINE COMPATIBILITY)
# =========================================================

@dataclass
class LinksScoredEvent:
    correlation_id: str
    node: Any
    scored_links: List[Any]

@dataclass
class NoLinksToScoreEvent:
    correlation_id : str 
    node: Any

@dataclass
class HighScoreLinksEvent:
    correlation_id  : str 
    node : Any
    links : Any

@dataclass 
class LowScoreLinksEvent:
    correlation_id :str 
    node : Any 
    links : Any
