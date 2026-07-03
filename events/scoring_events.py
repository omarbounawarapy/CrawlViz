from dataclasses import dataclass
from typing import Any, Literal

# =========================================================
# 1. ENQUEUE / BACKPRESSURE
# =========================================================

@dataclass
class ScoringEnqueuedEvent:
    correlation_id: str
    node_id: str
    queue_size: int


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
    correlation_id: str
    worker_id: int
    node_id: str


# =========================================================
# 4. SUCCESS INTERNAL COMPLETION
# =========================================================

@dataclass
class ScoringCompletedEvent:
    correlation_id: str
    node: Any
    scored_links: list[Any]
    output_count: int


# =========================================================
# 5. EMPTY RESULT (RETRY TRIGGER)
# =========================================================

@dataclass
class EmptyScoreResultsEvent:
    correlation_id: str
    node: Any


# =========================================================
# 6. FAILURE (STRICT DEBUG CONTEXT)
# =========================================================

@dataclass
class ScoringFailedEvent:
    correlation_id: str
    node: Any
    stage: Literal["SCORING_SERVICE"]
    error_type: str
    error_message: str


# =========================================================
# 7. DOWNSTREAM (PIPELINE COMPATIBILITY)
# =========================================================

@dataclass
class LinksScoredEvent:
    correlation_id: str
    node: Any
    scored_links: list[Any]


@dataclass
class NoLinksToScoreEvent:
    correlation_id: str
    node: Any


@dataclass
class HighScoreLinksEvent:
    correlation_id: str
    node: Any
    links: list[Any]


@dataclass
class LowScoreLinksEvent:
    correlation_id: str
    node: Any
    links: list[Any]
