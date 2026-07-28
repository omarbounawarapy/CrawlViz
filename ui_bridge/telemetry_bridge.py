"""
TelemetryBridge
================
EventBroker-facing component of the UI integration layer. Supersedes
UIEventTranslator (V1) -- same role, same invariants, much wider coverage.

Responsibilities (exactly these, nothing more):
  1. Receive a domain event via put().
  2. Update CrawlStateSnapshot to reflect the new state.
  3. Build and return zero or more strictly typed UI message dicts.
  4. Call UIWebSocketGateway.broadcast() with each of them.

Design invariants (unchanged from V1):
  - No queue.  No worker loop.  No asyncio.gather.
  - put() is the only entry point — called directly by the EventBroker
    dispatcher (already inside an asyncio.create_task).
  - Never emits events back into the EventBroker.
  - Never calls other pipelines.
  - All handler methods are synchronous; only put() and the broadcast
    call are async, which is the minimum required.

Why this file exists (see docs/V2_ARCHITECTURE.md §A.1.3, §B.2.1)
-------------------------------------------------------------------
An audit of every event this backend emits against every place it's
subscribed found that roughly a third of it reaches no consumer at all,
and of what IS consumed, only seven event types out of ~45 ever reached
the browser. Almost everything the V2 UI needs (pipeline throughput and
latency, which candidates the scoring cascade rejected or trusted without
an LLM call, the full NLP+LLM breakdown behind a node's score, pipeline
errors) was already being computed. This class is the fix: it is wired to
a much larger slice of the event graph and forwards it, still translating
domain events into the same kind of small, typed UI messages V1 used, just
covering the stages V1 didn't.

Message types this bridge produces
-----------------------------------
Unchanged from V1 (see docs/crawl_messages.ts):
    SNAPSHOT_FULL (via gateway, not this class), NODE_ADDED,
    NODE_STATE_CHANGED, NODE_EXPANDED, CRAWL_STOPPED

New in V2 (see docs/crawl_messages.ts):
    PIPELINE_EVENT       -- one pipeline stage's lifecycle tick
    CANDIDATE_EVALUATED  -- links the cascade evaluated but did not (all)
                            promote to a node -- the "what didn't happen" signal
    NODE_SCORED_DETAIL   -- the cascade's full explanation for one node's score
    NODE_ERROR           -- a pipeline failure, tied to a node where possible
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Dict, Optional
from urllib.parse import unquote

from .crawl_state_snapshot import CrawlStateSnapshot

log = logging.getLogger("ui_bridge.telemetry")

# Defensive cap on the url -> pending-detail correlation cache (see
# _on_priority_calculated / _on_node_added below). Only relevant if a link
# that was priority-scored somehow never becomes a node (e.g. the crawl's
# stop condition fires in the gap between the two events) -- normal
# operation drains this via pop() well before it matters.
_MAX_PENDING_DETAIL = 2000


class TelemetryBridge:
    """
    Thin, stateless-except-for-the-shared-snapshot translation layer.

    Wired into EventBroker exactly like LoggingPipeline / DebuggingPipeline
    — one subscribe() call per event type, one put() method. No queue sits
    between the broker and this class.
    """

    def __init__(
        self,
        snapshot: CrawlStateSnapshot,
        gateway,                        # UIWebSocketGateway — typed as Any to avoid circular import
        priority_strategy_name: str = "balanced",
    ) -> None:
        self.snapshot = snapshot
        self.gateway  = gateway
        self.priority_strategy_name = priority_strategy_name
        self._dispatch: Dict[type, Callable] = {}

        # stage start-time correlation, so PIPELINE_EVENT can report a real
        # duration_ms even though most *StartedEvent / *CompletedEvent pairs
        # don't carry timing themselves. Keyed by (stage, node_id).
        self._stage_started_at: Dict[tuple, float] = {}

        # url -> partial NODE_SCORED_DETAIL fields, populated when priority
        # is calculated (the last point a Link object with both its NLP
        # breakdown and LLM score is available) and consumed the moment the
        # resulting node actually appears (NodeAddedEvent). See the two
        # handlers for the full explanation of why this indirection exists.
        self._pending_detail: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Lifecycle — called once by crawler.start()
    # ------------------------------------------------------------------

    def register_handlers(self) -> None:
        """
        Bind event types to handler methods.

        Separated from __init__ so imports of event dataclasses happen
        after the full events package is initialised (same pattern used
        by other pipelines in the codebase).
        """
        from events import (
            ContentFilteredEvent,
            ExportBatchCompletedEvent,
            ExportBatchFailedEvent,
            ExportBatchStartedEvent,
            ExportRowFailedEvent,
            ExtractionStartedEvent,
            FilteringEnqueuedEvent,
            FilteringPipelineErrorEvent,
            FilteringWorkerCycleStartedEvent,
            HighScoreLinksEvent,
            ItemExtractionCompletedEvent,
            LinkExtractionCompletedEvent,
            LinksScoredEvent,
            LowScoreLinksEvent,
            NodeAddedEvent,
            PageFetchedEvent,
            PriorityCalculatedEvent,
            PriorityCalculationFailedEvent,
            PriorityCalculationStartedEvent,
            ProcessingExtractionFailedEvent,
            RequestEnqueuedEvent,
            RequestFailedEvent,
            RequestResponseReceivedEvent,
            RequestStartedEvent,
            RetryOperationFailedEvent,
            ScoringCompletedEvent,
            ScoringEnqueuedEvent,
            ScoringFailedEvent,
            ScoringStartedEvent,
            StopCrawlEvent,
            StorageNodeUpdatedEvent,
            StorageOperationFailedEvent,
            TransformationCompletedEvent,
            TransformationFailedEvent,
            TransformationStartedEvent,
        )

        self._dispatch = {
            # --- V1 node lifecycle (unchanged behavior)
            NodeAddedEvent:          self._on_node_added,
            PageFetchedEvent:        self._on_page_fetched,
            ContentFilteredEvent:    self._on_content_filtered,
            LinksScoredEvent:        self._on_links_scored,
            PriorityCalculatedEvent: self._on_priority_calculated,
            StorageNodeUpdatedEvent: self._on_node_updated,
            StopCrawlEvent:          self._on_crawl_stopped,

            # --- V2: request stage
            RequestEnqueuedEvent:         self._on_request_enqueued,
            RequestStartedEvent:          self._on_request_started,
            RequestResponseReceivedEvent: self._on_request_completed,
            RequestFailedEvent:           self._on_request_failed,

            # --- V2: extraction stage
            ExtractionStartedEvent:          self._on_extraction_started,
            LinkExtractionCompletedEvent:    self._on_extraction_links_done,
            ItemExtractionCompletedEvent:    self._on_extraction_items_done,
            ProcessingExtractionFailedEvent: self._on_extraction_failed,

            # --- V2: filtering stage
            FilteringEnqueuedEvent:          self._on_filtering_enqueued,
            FilteringWorkerCycleStartedEvent: self._on_filtering_started,
            FilteringPipelineErrorEvent:     self._on_filtering_failed,

            # --- V2: scoring stage (+ cascade candidate visibility)
            ScoringEnqueuedEvent:  self._on_scoring_enqueued,
            ScoringStartedEvent:   self._on_scoring_started,
            ScoringCompletedEvent: self._on_scoring_completed,
            ScoringFailedEvent:    self._on_scoring_failed,
            HighScoreLinksEvent:   self._on_high_score_links,
            LowScoreLinksEvent:    self._on_low_score_links,

            # --- V2: priority stage
            PriorityCalculationStartedEvent: self._on_priority_started,
            PriorityCalculationFailedEvent:  self._on_priority_failed,

            # --- V2: transformation stage
            TransformationStartedEvent:   self._on_transformation_started,
            TransformationCompletedEvent: self._on_transformation_completed,
            TransformationFailedEvent:    self._on_transformation_failed,

            # --- V2: export stage
            ExportBatchStartedEvent:   self._on_export_started,
            ExportBatchCompletedEvent: self._on_export_completed,
            ExportBatchFailedEvent:    self._on_export_failed,
            ExportRowFailedEvent:      self._on_export_row_failed,

            # --- V2: crawl-wide errors
            StorageOperationFailedEvent: self._on_storage_failed,
            RetryOperationFailedEvent:   self._on_retry_failed,
        }

    # ------------------------------------------------------------------
    # EventBroker entry point
    # ------------------------------------------------------------------

    async def put(self, event) -> None:
        """
        Called by EventBroker for each subscribed event.

        No queue. Translate synchronously, broadcast asynchronously. A
        handler may return one message dict, a list of them, or None.
        """
        handler = self._dispatch.get(type(event))
        if handler is None:
            return

        try:
            result = handler(event)
            if result is None:
                return
            messages = result if isinstance(result, list) else [result]
            for message in messages:
                if message is not None:
                    await self.gateway.broadcast(message)
        except Exception:
            log.exception("Translation failed for event %s", type(event).__name__)

    # ==================================================================
    # V1 handlers — node lifecycle (unchanged from UIEventTranslator)
    # ==================================================================

    def _on_node_added(self, event) -> list:
        node      = event.node
        node_id   = str(node.get_id())
        url       = unquote(node.link.url)
        parent_id = str(node.parent.get_id()) if node.parent and node.parent != "" else None
        record = self.snapshot.add_node(
            node_id=node_id,
            url=url,
            depth=node.get_depth(),
            priority=node.get_priority(),
            llm_score=node.get_llm_score(),
            parent_id=parent_id,
        )
        self.snapshot.increment("nodes_created")

        messages = [{
            "type": "NODE_ADDED",
            "ts":   time.time(),
            "node": record.to_dict(),
        }]

        # If this node's link went through the scoring cascade (it almost
        # always will -- the only nodes that don't are seeds), the pending
        # cache populated in _on_priority_calculated has its NLP breakdown
        # and LLM score waiting under this same URL. Consume it now that a
        # real node_id exists to key it by.
        pending = self._pending_detail.pop(url, None)
        if pending is not None:
            detail = self.snapshot.set_node_detail(
                node_id=node_id,
                nlp_score=pending.get("nlp_score"),
                nlp_breakdown=pending.get("nlp_breakdown"),
                llm_score=pending.get("llm_score"),
                priority=pending.get("priority"),
                priority_strategy=self.priority_strategy_name,
            )
            messages.append({
                "type": "NODE_SCORED_DETAIL",
                "ts":   time.time(),
                **detail.to_dict(),
            })

        return messages

    def _on_page_fetched(self, event) -> dict:
        node_id = str(event.node.get_id())
        self.snapshot.set_node_state(node_id, "FETCHED")
        self.snapshot.increment("nodes_fetched")

        return {
            "type":    "NODE_STATE_CHANGED",
            "ts":      time.time(),
            "node_id": node_id,
            "state":   "FETCHED",
        }

    def _on_content_filtered(self, event) -> dict:
        node_id = str(event.node.get_id())
        self.snapshot.set_node_state(node_id, "FILTERED")
        self.snapshot.increment("nodes_filtered")
        self.snapshot.increment("total_links_found", by=event.accepted_links_count)

        return {
            "type":            "NODE_STATE_CHANGED",
            "ts":              time.time(),
            "node_id":         node_id,
            "state":           "FILTERED",
            "links_accepted":  event.accepted_links_count,
            "links_rejected":  event.rejected_links_count,
            "items_accepted":  event.accepted_items_count,
        }

    def _on_links_scored(self, event) -> dict:
        node_id = str(event.node.get_id())
        self.snapshot.set_node_state(node_id, "SCORED")
        self.snapshot.increment("nodes_scored")

        return {
            "type":         "NODE_STATE_CHANGED",
            "ts":           time.time(),
            "node_id":      node_id,
            "state":        "SCORED",
            "scored_count": len(event.scored_links),
        }

    def _on_priority_calculated(self, event) -> dict:
        parent_id = str(event.parent.get_id())
        self.snapshot.set_node_state(parent_id, "EXPANDED")
        self.snapshot.increment("nodes_expanded")

        # Stash each child's cascade breakdown under its (not-yet-a-node)
        # URL so _on_node_added can attach it once the node itself exists.
        # This is the only point in the pipeline where a Link object still
        # carries both its NLP vector *and* its LLM score (if any) together
        # -- one hop later, StoragePipeline mints a fresh Node and the Link
        # is no longer directly reachable from any subsequent event.
        for entry in event.links:
            link = entry["link"]
            url = unquote(link.url)
            if len(self._pending_detail) >= _MAX_PENDING_DETAIL:
                self._pending_detail.pop(next(iter(self._pending_detail)))
            self._pending_detail[url] = {
                "nlp_score": getattr(link, "_nlp_score", None),
                "nlp_breakdown": dict(getattr(link, "nlp_vector", {}) or {}),
                "llm_score": entry.get("score") or None,
                "priority": entry.get("priority"),
            }

        return {
            "type":           "NODE_EXPANDED",
            "ts":             time.time(),
            "parent_id":      parent_id,
            "children_count": len(event.links),
            "children": [
                {
                    "url":      unquote(link["link"].url),
                    "score":    link["score"],
                    "priority": link["priority"],
                }
                for link in event.links
            ],
        }

    def _on_node_updated(self, event) -> Optional[dict]:
        # Items are now persisted; update metric only. Not broadcast — too
        # granular as its own message (unchanged judgment call from V1) --
        # but every item that lands here already showed up as a
        # PIPELINE_EVENT completed tick for the transformation stage.
        self.snapshot.increment("total_items_stored", by=len(event.items))
        return None

    def _on_crawl_stopped(self, event) -> dict:
        self.snapshot.mark_stopped(event.reason)

        return {
            "type":       "CRAWL_STOPPED",
            "ts":         time.time(),
            "reason":     event.reason,
            "node_count": event.node_count,
            "max_depth":  event.max_depth,
            "duration":   event.duration,
            "detail":     event.detail,
            "metrics":    self.snapshot.metrics.to_dict(),
        }

    # ==================================================================
    # V2 handlers — shared helpers
    # ==================================================================

    def _tick(
        self,
        *,
        stage: str,
        phase: str,
        node_id: Optional[str] = None,
        worker_id: Optional[int] = None,
        queue_size: Optional[int] = None,
        detail: Optional[str] = None,
    ) -> dict:
        """Record one pipeline lifecycle tick and build its PIPELINE_EVENT
        message. Shared by every V2 stage handler below so the
        started->completed/failed duration correlation lives in one place.
        """
        duration_ms = None
        key = (stage, node_id)

        if phase == "started" and node_id is not None:
            self._stage_started_at[key] = time.monotonic()
        elif phase in ("completed", "failed") and node_id is not None:
            start = self._stage_started_at.pop(key, None)
            if start is not None:
                duration_ms = round((time.monotonic() - start) * 1000, 2)

        self.snapshot.record_pipeline_event(
            stage=stage, phase=phase, queue_size=queue_size, duration_ms=duration_ms,
        )

        return {
            "type":        "PIPELINE_EVENT",
            "ts":          time.time(),
            "stage":       stage,
            "phase":       phase,
            "node_id":     node_id,
            "worker_id":   worker_id,
            "queue_size":  queue_size,
            "duration_ms": duration_ms,
            "detail":      detail,
        }

    def _error(self, *, node_id: Optional[str], stage: str, error_type: str, error_message: str) -> dict:
        self.snapshot.add_error(
            node_id=node_id, stage=stage, error_type=error_type, error_message=error_message,
        )
        return {
            "type":          "NODE_ERROR",
            "ts":            time.time(),
            "node_id":       node_id,
            "stage":         stage,
            "error_type":    error_type,
            "error_message": error_message,
        }

    # ==================================================================
    # V2 handlers — request stage
    # ==================================================================

    def _on_request_enqueued(self, event) -> dict:
        return self._tick(stage="request", phase="enqueued", node_id=event.node_id, queue_size=event.queue_size)

    def _on_request_started(self, event) -> dict:
        return self._tick(stage="request", phase="started", node_id=event.node_id, worker_id=event.worker_id, detail=event.url)

    def _on_request_completed(self, event) -> dict:
        return self._tick(stage="request", phase="completed", node_id=event.node_id, detail=f"{event.response_size} B")

    def _on_request_failed(self, event) -> list:
        node_id = str(event.node.get_id())
        return [
            self._tick(stage="request", phase="failed", node_id=node_id, detail=event.error_message),
            self._error(node_id=node_id, stage="request", error_type=event.error_type, error_message=event.error_message),
        ]

    # ==================================================================
    # V2 handlers — extraction stage (ProcessingPipeline)
    # ==================================================================

    def _on_extraction_started(self, event) -> dict:
        return self._tick(stage="extraction", phase="started", node_id=event.node_id, worker_id=event.worker_id)

    def _on_extraction_links_done(self, event) -> dict:
        return self._tick(stage="extraction", phase="completed", node_id=event.node_id, detail=f"{event.extracted_links_count} links")

    def _on_extraction_items_done(self, event) -> None:
        # Second half of the same extraction call (_on_extraction_links_done
        # already closed out the started->completed pair for this node);
        # folded into the metrics via the links-done tick rather than
        # double-counting a second "completed" for one extraction pass.
        return None

    def _on_extraction_failed(self, event) -> list:
        node_id = str(event.node.get_id())
        return [
            self._tick(stage="extraction", phase="failed", node_id=node_id, detail=event.error_message),
            self._error(node_id=node_id, stage="extraction", error_type=event.error_type, error_message=event.error_message),
        ]

    # ==================================================================
    # V2 handlers — filtering stage
    # ==================================================================

    def _on_filtering_enqueued(self, event) -> dict:
        return self._tick(stage="filtering", phase="enqueued", node_id=event.node_id, queue_size=event.queue_size)

    def _on_filtering_started(self, event) -> dict:
        return self._tick(stage="filtering", phase="started", node_id=event.node_id, worker_id=event.worker_id)

    def _on_filtering_failed(self, event) -> list:
        node_id = str(event.node.get_id())
        return [
            self._tick(stage="filtering", phase="failed", node_id=node_id, detail=event.error_message),
            self._error(node_id=node_id, stage="filtering", error_type=event.error_type, error_message=event.error_message),
        ]

    # ==================================================================
    # V2 handlers — scoring stage + cascade candidate visibility
    # ==================================================================

    def _on_scoring_enqueued(self, event) -> dict:
        return self._tick(stage="scoring", phase="enqueued", node_id=event.node_id, queue_size=event.queue_size)

    def _on_scoring_started(self, event) -> dict:
        return self._tick(stage="scoring", phase="started", node_id=event.node_id, worker_id=event.worker_id)

    def _on_scoring_completed(self, event) -> dict:
        node_id = str(event.node.get_id())
        return self._tick(stage="scoring", phase="completed", node_id=node_id, detail=f"{event.output_count} sent to LLM")

    def _on_scoring_failed(self, event) -> list:
        node_id = str(event.node.get_id())
        return [
            self._tick(stage="scoring", phase="failed", node_id=node_id, detail=event.error_message),
            self._error(node_id=node_id, stage="scoring", error_type=event.error_type, error_message=event.error_message),
        ]

    def _candidate_message(self, event, decision: str) -> Optional[dict]:
        """Shared by _on_high_score_links / _on_low_score_links -- these are
        the two cascade buckets that (respectively) skip the LLM because
        the NLP signal is already confident, or get dropped outright. This
        is the direct fix for the "what didn't happen" blind spot (see
        docs/V2_ARCHITECTURE.md §A.2.3): without this, links the cascade
        rejects or fast-tracks leave no trace anywhere in the UI.
        """
        if not event.links:
            return None

        parent_id = str(event.node.get_id())
        candidates = []
        for link in event.links:
            nlp_score = getattr(link, "_nlp_score", 0.0)
            breakdown = dict(getattr(link, "nlp_vector", {}) or {})
            self.snapshot.add_candidate(
                parent_id=parent_id, url=unquote(link.url), nlp_score=nlp_score,
                decision=decision, nlp_breakdown=breakdown,
            )
            candidates.append({
                "url": unquote(link.url),
                "nlp_score": nlp_score,
                "nlp_breakdown": breakdown,
            })

        return {
            "type":       "CANDIDATE_EVALUATED",
            "ts":         time.time(),
            "parent_id":  parent_id,
            "decision":   decision,
            "candidates": candidates,
        }

    def _on_high_score_links(self, event) -> Optional[dict]:
        return self._candidate_message(event, "trusted_no_llm")

    def _on_low_score_links(self, event) -> Optional[dict]:
        return self._candidate_message(event, "dropped")

    # ==================================================================
    # V2 handlers — priority stage
    # ==================================================================

    def _on_priority_started(self, event) -> dict:
        return self._tick(stage="priority", phase="started", node_id=event.node_id, worker_id=event.worker_id)

    def _on_priority_failed(self, event) -> list:
        node_id = str(event.node.get_id())
        return [
            self._tick(stage="priority", phase="failed", node_id=node_id, detail=event.error_message),
            self._error(node_id=node_id, stage="priority", error_type=event.error_type, error_message=event.error_message),
        ]

    # ==================================================================
    # V2 handlers — transformation stage
    # ==================================================================

    def _on_transformation_started(self, event) -> dict:
        return self._tick(stage="transformation", phase="started", node_id=event.node_id, worker_id=event.worker_id)

    def _on_transformation_completed(self, event) -> dict:
        node_id = str(event.node.get_id())
        return self._tick(stage="transformation", phase="completed", node_id=node_id, detail=f"{event.output_count} items")

    def _on_transformation_failed(self, event) -> list:
        node_id = str(event.node.get_id())
        return [
            self._tick(stage="transformation", phase="failed", node_id=node_id, detail=event.error_message),
            self._error(node_id=node_id, stage="transformation", error_type=event.error_type, error_message=event.error_message),
        ]

    # ==================================================================
    # V2 handlers — export stage (table-level, not node-level)
    # ==================================================================

    def _on_export_started(self, event) -> dict:
        return self._tick(stage="export", phase="started", detail=f"{event.table} (batch={event.batch_size})")

    def _on_export_completed(self, event) -> dict:
        # This is the one V1 event that already carried its own duration --
        # honor it instead of the started/completed correlation, since export
        # batches aren't tracked per-node the way every other stage is.
        self.snapshot.record_pipeline_event(stage="export", phase="completed", duration_ms=event.duration_ms)
        return {
            "type": "PIPELINE_EVENT", "ts": time.time(), "stage": "export", "phase": "completed",
            "node_id": None, "worker_id": None, "queue_size": None,
            "duration_ms": event.duration_ms, "detail": f"{event.table}: {event.inserted_count} rows",
        }

    def _on_export_failed(self, event) -> list:
        return [
            self._tick(stage="export", phase="failed", detail=f"{event.table}: {event.error_message}"),
            self._error(node_id=None, stage="export", error_type=event.error_type, error_message=event.error_message),
        ]

    def _on_export_row_failed(self, event) -> dict:
        return self._error(
            node_id=None, stage="export",
            error_type=event.error_type,
            error_message=f"{event.table}.{event.field}: {event.value!r}",
        )

    # ==================================================================
    # V2 handlers — crawl-wide failures
    # ==================================================================

    def _on_storage_failed(self, event) -> dict:
        return self._error(
            node_id=event.correlation_id, stage="storage",
            error_type=event.error_type, error_message=event.error_message,
        )

    def _on_retry_failed(self, event) -> dict:
        return self._error(
            node_id=event.correlation_id, stage=f"retry:{event.stage}",
            error_type=event.error_type, error_message=event.error_message,
        )
