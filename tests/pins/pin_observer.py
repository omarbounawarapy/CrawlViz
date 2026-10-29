"""The runner component that hears a pin crawl's events.

It records two things: the cascade's per-link decisions, and the UI messages
the ``TelemetryBridge`` would broadcast for the same events. It only listens:
it never emits events or holds one up, so a crawl visits the same pages with it
as without it (``test_pin_crawl.py`` checks this).

Recording closes when the last page of the budget is requested. In lockstep
everything before that is ordered by the event bus; what follows (the last
page's own events, its scoring, the stop) races with the runner stopping the
crawl, so it is left out. Only the stop message is kept, reduced to the fields
that do not depend on that race.
"""
from collections.abc import Callable, Coroutine
from typing import Any

from pin_doubles import RecordingGateway

from events import (
    HighScoreLinksEvent,
    LowScoreLinksEvent,
    PriorityCalculatedEvent,
    RequestStartedEvent,
    StopCrawlEvent,
)
from ui_bridge import CrawlStateSnapshot, TelemetryBridge

# What the CRAWL_STOPPED message keeps: its counts depend on when the stop landed.
STOP_MESSAGE_KEYS = ("type", "reason")

DecisionEvent = HighScoreLinksEvent | LowScoreLinksEvent | PriorityCalculatedEvent


class PinObserver:
    """Subscribed like a pipeline: ``handlers`` names the events it receives."""

    def __init__(self, budget: int) -> None:
        self.budget = budget
        self.requests_started = 0
        self.closed = False
        self.gateway = RecordingGateway()
        self.bridge = TelemetryBridge(CrawlStateSnapshot(), self.gateway)
        self.bridge.register_handlers()
        self.decisions: list[tuple[int, dict[str, Any]]] = []
        # Every event the bridge translates, which includes the three decision events.
        self.handlers: dict[type, Callable[[Any], Coroutine[Any, Any, None]]] = {
            event_type: self.put for event_type in self.bridge.event_types
        }

    async def start(self) -> None:
        pass

    async def put(self, event: object) -> None:
        if isinstance(event, RequestStartedEvent):
            self.requests_started += 1
            self.closed = self.closed or self.requests_started >= self.budget
        if self.closed and not isinstance(event, StopCrawlEvent):
            return
        if isinstance(event, DecisionEvent):
            self._record_decision(event)
        await self.bridge.put(event)

    def _record_decision(self, event: DecisionEvent) -> None:
        if isinstance(event, PriorityCalculatedEvent):
            kind, node = "priority_calculated", event.parent
        else:
            is_high = isinstance(event, HighScoreLinksEvent)
            kind = "high_score_links" if is_high else "low_score_links"
            node = event.node
        for record in event.records:
            self.decisions.append((event.seq, {
                "decision": kind, "seq": event.seq, "node_id": node.get_id(), **record,
            }))

    def wire_messages(self) -> list[dict[str, Any]]:
        return [
            {key: message[key] for key in STOP_MESSAGE_KEYS}
            if message["type"] == "CRAWL_STOPPED" else message
            for message in self.gateway.messages
        ]

    def link_scores(self) -> list[dict[str, Any]]:
        """Decisions in the order the broker emitted them (``seq``), not the order
        their handler tasks happened to run."""
        return [record for _, record in sorted(self.decisions, key=lambda item: item[0])]
