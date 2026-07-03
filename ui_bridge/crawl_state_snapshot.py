"""
CrawlStateSnapshot
==================
Pure data container.  No async.  No network.  No event handling.

Holds the full UI-visible state of one crawl run.  Written exclusively
by UIEventTranslator; read by UIWebSocketGateway (for catch-up snapshots).

Node lifecycle states
---------------------
CREATED → FETCHED → FILTERED → SCORED → EXPANDED
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Value objects
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
# Snapshot
# ---------------------------------------------------------------------------

class CrawlStateSnapshot:
    """
    Mutable store of live crawl state.

    All writes arrive from UIEventTranslator, which runs inside the single
    asyncio event loop — no locking required.
    """

    def __init__(self) -> None:
        self.status:      str                  = "RUNNING"  # RUNNING | STOPPED
        self.stop_reason: Optional[str]        = None
        self.metrics:     CrawlMetrics         = CrawlMetrics()
        self._nodes:      Dict[str, NodeRecord] = {}

    # ------------------------------------------------------------------
    # Node writes
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
        }
