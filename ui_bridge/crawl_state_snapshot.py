"""
CrawlStateSnapshot
==================
Pure data container.  No async.  No network.  No event handling.

Holds the full UI-visible state of one crawl run.  Written exclusively
by TelemetryBridge; read by UIWebSocketGateway (for catch-up snapshots).

Node lifecycle states
---------------------
CREATED → FETCHED → FILTERED → SCORED → EXPANDED

V2 additions (see docs/V2_ARCHITECTURE.md §B.2.1-2)
----------------------------------------------------
Everything below "V2 additions" was added to close the "telemetry chasm"
finding: most of the backend's own instrumentation was already being
computed and then discarded before it ever reached this snapshot. These
additions don't change anything about the V1 fields above them -- they're
new, independent pieces of state fed by events that previously had zero
subscribers.

- ``pipeline_stats``: running per-stage counters (started/completed/failed,
  last observed queue depth, duration) -- the data source for the Pipeline
  Monitor.
- ``candidates``: links the scoring cascade evaluated but that did *not*
  become a full node (dropped for low confidence, or trusted and fast-tracked
  without an LLM call). This is the "what didn't happen" signal -- see
  docs/V2_ARCHITECTURE.md §A.2.3. Bounded with a deque so a very long crawl
  can't grow this unboundedly.
- ``node_details``: the cascade's full explanation for a node's score
  (NLP sub-signals + weights, LLM score, final priority), keyed by node_id --
  the data source for the Node Inspector's Scoring tab.
- ``errors``: pipeline failures, now that the two previously-orphaned
  failure event types are wired up (§A.1.2).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Deque, Dict, List, Optional


# ---------------------------------------------------------------------------
# Value objects — V1 (unchanged)
# ---------------------------------------------------------------------------

@dataclass
class NodeRecord:
    node_id:    str
    url:        str
    depth:      int
    priority:   float
    llm_score:  float
    parent_id:  Optional[str]
    state:      str             # CREATED | FETCHED | FILTERED | SCORED | EXPANDED
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CrawlMetrics:
    nodes_created:      int   = 0
    nodes_fetched:      int   = 0
    nodes_filtered:     int   = 0
    nodes_scored:       int   = 0
    nodes_expanded:     int   = 0
    total_links_found:  int   = 0
    total_items_stored: int   = 0
    start_time:         float = field(default_factory=time.time)
    elapsed_seconds:    float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Value objects — V2 additions
# ---------------------------------------------------------------------------

# Every pipeline stage this build reports on. Kept as an explicit tuple
# (rather than inferring it from whatever shows up first) so the frontend
# always receives a stable, fully-populated set of stages even before any
# events have arrived for a given one -- one fewer "is this key present yet"
# check on the client.
PIPELINE_STAGES: tuple = (
    "request", "extraction", "filtering", "scoring",
    "priority", "transformation", "export",
)

# Bounds on unbounded-growth collections. Generous relative to the default
# blueprint's max_nodes (500) -- a few thousand candidate evaluations or
# errors is a realistic ceiling for a single run; this just protects against
# a pathological very-long crawl growing the snapshot without limit.
_MAX_CANDIDATES = 4000
_MAX_ERRORS = 1000


@dataclass
class StageStats:
    """Running counters for one pipeline stage. Updated incrementally as
    PIPELINE_EVENT-worthy events arrive; never recomputed from scratch."""
    started:          int = 0
    completed:        int = 0
    failed:           int = 0
    queue_size:       int = 0     # last observed enqueue-time queue depth
    last_duration_ms: Optional[float] = None
    _total_duration_ms: float = field(default=0.0, repr=False)
    _duration_samples:  int   = field(default=0, repr=False)

    def to_dict(self) -> dict:
        avg = (
            self._total_duration_ms / self._duration_samples
            if self._duration_samples else None
        )
        return {
            "started":          self.started,
            "completed":        self.completed,
            "failed":           self.failed,
            "queue_size":       self.queue_size,
            "last_duration_ms": self.last_duration_ms,
            "avg_duration_ms":  avg,
        }


@dataclass
class CandidateRecord:
    """A link the cascade evaluated that did not (or has not yet) become a
    full graph node -- either dropped outright (low NLP confidence, cost
    budget exhausted) or trusted without an LLM call (high NLP confidence)."""
    parent_id:     str
    url:           str
    nlp_score:     float
    decision:      str                    # "dropped" | "trusted_no_llm"
    nlp_breakdown: Dict[str, float] = field(default_factory=dict)
    ts:            float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NodeDetailRecord:
    """The cascade's full explanation for one node's score -- enrichment
    data for the Node Inspector, sent in addition to (not instead of) the
    lean NodeRecord used for the graph."""
    node_id:            str
    nlp_score:          Optional[float] = None
    nlp_breakdown:       Dict[str, float] = field(default_factory=dict)
    llm_score:           Optional[float] = None
    priority:            Optional[float] = None
    priority_strategy:   Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ErrorRecord:
    node_id:       Optional[str]
    stage:         str
    error_type:    str
    error_message: str
    ts:            float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

class CrawlStateSnapshot:
    """
    Mutable store of live crawl state.

    All writes arrive from TelemetryBridge, which runs inside the single
    asyncio event loop — no locking required.
    """

    def __init__(self) -> None:
        self.status:      str                  = "RUNNING"  # RUNNING | STOPPED
        self.stop_reason: Optional[str]        = None
        self.metrics:     CrawlMetrics         = CrawlMetrics()
        self._nodes:      Dict[str, NodeRecord] = {}

        # V2 additions
        self.pipeline_stats: Dict[str, StageStats] = {
            stage: StageStats() for stage in PIPELINE_STAGES
        }
        self._candidates: Deque[CandidateRecord] = deque(maxlen=_MAX_CANDIDATES)
        self._node_details: Dict[str, NodeDetailRecord] = {}
        self._errors: Deque[ErrorRecord] = deque(maxlen=_MAX_ERRORS)

    # ------------------------------------------------------------------
    # Node writes (V1, unchanged)
    # ------------------------------------------------------------------

    def add_node(
        self,
        *,
        node_id:   str,
        url:       str,
        depth:     int,
        priority:  float,
        llm_score: float,
        parent_id: Optional[str],
        state:     str = "CREATED",
    ) -> NodeRecord:
        record = NodeRecord(
            node_id=node_id,
            url=url,
            depth=depth,
            priority=priority,
            llm_score=llm_score,
            parent_id=parent_id,
            state=state,
        )
        self._nodes[node_id] = record
        return record

    def set_node_state(self, node_id: str, state: str) -> None:
        node = self._nodes.get(node_id)
        if node:
            node.state = state

    # ------------------------------------------------------------------
    # Metric writes  (named-counter approach keeps the API stable)
    # ------------------------------------------------------------------

    def increment(self, counter: str, by: int = 1) -> None:
        """Increment any CrawlMetrics field by name. Silently ignores unknown names."""
        if hasattr(self.metrics, counter):
            setattr(self.metrics, counter, getattr(self.metrics, counter) + by)

    # ------------------------------------------------------------------
    # Crawl-level writes
    # ------------------------------------------------------------------

    def mark_stopped(self, reason: str) -> None:
        self.status      = "STOPPED"
        self.stop_reason = reason
        self.metrics.elapsed_seconds = time.time() - self.metrics.start_time

    # ------------------------------------------------------------------
    # V2 writes
    # ------------------------------------------------------------------

    def record_pipeline_event(
        self,
        *,
        stage:       str,
        phase:       str,               # "enqueued" | "started" | "completed" | "failed"
        queue_size:  Optional[int] = None,
        duration_ms: Optional[float] = None,
    ) -> None:
        stats = self.pipeline_stats.setdefault(stage, StageStats())

        if phase == "enqueued" and queue_size is not None:
            stats.queue_size = queue_size
        elif phase == "started":
            stats.started += 1
        elif phase == "completed":
            stats.completed += 1
            if duration_ms is not None:
                stats.last_duration_ms = duration_ms
                stats._total_duration_ms += duration_ms
                stats._duration_samples += 1
        elif phase == "failed":
            stats.failed += 1

    def add_candidate(
        self,
        *,
        parent_id: str,
        url: str,
        nlp_score: float,
        decision: str,
        nlp_breakdown: Optional[Dict[str, float]] = None,
    ) -> CandidateRecord:
        record = CandidateRecord(
            parent_id=parent_id,
            url=url,
            nlp_score=nlp_score,
            decision=decision,
            nlp_breakdown=nlp_breakdown or {},
        )
        self._candidates.append(record)
        return record

    def set_node_detail(
        self,
        *,
        node_id: str,
        nlp_score: Optional[float] = None,
        nlp_breakdown: Optional[Dict[str, float]] = None,
        llm_score: Optional[float] = None,
        priority: Optional[float] = None,
        priority_strategy: Optional[str] = None,
    ) -> NodeDetailRecord:
        record = NodeDetailRecord(
            node_id=node_id,
            nlp_score=nlp_score,
            nlp_breakdown=nlp_breakdown or {},
            llm_score=llm_score,
            priority=priority,
            priority_strategy=priority_strategy,
        )
        self._node_details[node_id] = record
        return record

    def add_error(
        self,
        *,
        node_id: Optional[str],
        stage: str,
        error_type: str,
        error_message: str,
    ) -> ErrorRecord:
        record = ErrorRecord(
            node_id=node_id,
            stage=stage,
            error_type=error_type,
            error_message=error_message,
        )
        self._errors.append(record)
        return record

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def node_list(self) -> List[dict]:
        return [n.to_dict() for n in self._nodes.values()]

    def to_full_snapshot(self) -> dict:
        """Called by UIWebSocketGateway when a new client connects."""
        self.metrics.elapsed_seconds = time.time() - self.metrics.start_time
        return {
            "type":        "SNAPSHOT_FULL",
            "status":      self.status,
            "stop_reason": self.stop_reason,
            "metrics":     self.metrics.to_dict(),
            "nodes":       self.node_list(),
            # V2 additions
            "pipeline_stats": {k: v.to_dict() for k, v in self.pipeline_stats.items()},
            "candidates":     [c.to_dict() for c in self._candidates],
            "node_details":   {k: v.to_dict() for k, v in self._node_details.items()},
            "errors":         [e.to_dict() for e in self._errors],
        }
