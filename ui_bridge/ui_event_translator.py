"""
UIEventTranslator
=================
EventBroker-facing component of the UI integration layer.

Responsibilities (exactly these, nothing more):
  1. Receive a domain event via put().
  2. Update CrawlStateSnapshot to reflect the new state.
  3. Build and return a strictly typed UI message dict.
  4. Call UIWebSocketGateway.broadcast() with that message.

Design invariants:
  - No queue.  No worker loop.  No asyncio.gather.
  - put() is the only entry point — called directly by the EventBroker
    dispatcher (already inside an asyncio.create_task).
  - Never emits events back into the EventBroker.
  - Never calls other pipelines.
  - All handler methods are synchronous; only put() and the broadcast
    call are async, which is the minimum required.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Dict, Optional
from urllib.parse import unquote

from .crawl_state_snapshot import CrawlStateSnapshot

log = logging.getLogger("ui_bridge.translator")


class UIEventTranslator:
    """
    Thin, stateless (except for the shared snapshot) translation layer.

    Wired into EventBroker exactly like LoggingPipeline — one subscribe()
    call, one put() method.  No queue sits between the broker and this class.
    """

    def __init__(
        self,
        snapshot: CrawlStateSnapshot,
        gateway,                        # UIWebSocketGateway — typed as Any to avoid circular import
    ) -> None:
        self.snapshot = snapshot
        self.gateway  = gateway
        self._dispatch: Dict[type, Callable] = {}

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
            NodeAddedEvent,
            PageFetchedEvent,
            ContentFilteredEvent,
            LinksScoredEvent,
            PriorityCalculatedEvent,
            StorageNodeUpdatedEvent,
        )
        from events import StopCrawlEvent

        self._dispatch = {
            NodeAddedEvent:          self._on_node_added,
            PageFetchedEvent:        self._on_page_fetched,
            ContentFilteredEvent:    self._on_content_filtered,
            LinksScoredEvent:        self._on_links_scored,
            PriorityCalculatedEvent: self._on_priority_calculated,
            StorageNodeUpdatedEvent: self._on_node_updated,
            StopCrawlEvent:          self._on_crawl_stopped,
        }

    # ------------------------------------------------------------------
    # EventBroker entry point
    # ------------------------------------------------------------------

    async def put(self, event) -> None:
        """
        Called by EventBroker for each subscribed event.

        No queue.  Translate synchronously, broadcast asynchronously.
        """
        handler = self._dispatch.get(type(event))
        if handler is None:
            return

        try:
            message: Optional[dict] = handler(event)
            if message is not None:
                await self.gateway.broadcast(message)
        except Exception:
            log.exception("Translation failed for event %s", type(event).__name__)

    # ------------------------------------------------------------------
    # Handlers — synchronous, return a typed UI message dict or None.
    #
    # Each handler does exactly two things:
    #   (a) mutate snapshot
    #   (b) return the UI message that represents that mutation
    # ------------------------------------------------------------------

    def _on_node_added(self, event) -> dict:
        node      = event.node
        node_id   = str(node.get_id())
        parent_id = str(node.parent.get_id()) if node.parent and node.parent != "" else None
        record = self.snapshot.add_node(
            node_id=node_id,
            url=unquote(node.link.url),
            depth=node.get_depth(),
            priority=node.get_priority(),
            llm_score=node.get_llm_score(),
            parent_id=parent_id,
        )
        self.snapshot.increment("nodes_created")

        return {
            "type": "NODE_ADDED",
            "ts":   time.time(),
            "node": record.to_dict(),
        }

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
        # Items are now persisted; update metric only.  Not broadcast — too granular.
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
