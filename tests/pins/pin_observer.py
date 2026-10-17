"""The runner component that hears a pin crawl's events.

It records two things: the cascade's per-link decisions, and the UI messages
the ``TelemetryBridge`` would broadcast for the same events.
"""
from collections.abc import Callable, Coroutine
from typing import Any

from pin_doubles import RecordingGateway

from events import HighScoreLinksEvent, LowScoreLinksEvent, PriorityCalculatedEvent
from ui_bridge import CrawlStateSnapshot, TelemetryBridge

DecisionEvent = HighScoreLinksEvent | LowScoreLinksEvent | PriorityCalculatedEvent


class PinObserver:
    """Subscribed like a pipeline: ``handlers`` names the events it receives."""

    def __init__(self) -> None:
        self.gateway = RecordingGateway()
        self.bridge = TelemetryBridge(CrawlStateSnapshot(), self.gateway)
        self.bridge.register_handlers()
        self.decisions: list[tuple[int, dict[str, Any]]] = []
        # Every event the bridge translates, which includes the three decision events.
        self.handlers: dict[type, Callable[[Any], Coroutine[Any, Any, None]]] = {
            event_type: self.put for event_type in self.bridge._dispatch
        }

    async def start(self) -> None:
        pass

    async def put(self, event: object) -> None:
        if isinstance(event, (HighScoreLinksEvent, LowScoreLinksEvent, PriorityCalculatedEvent)):
            self._record_decision(event)
        await self.bridge.put(event)

    def _record_decision(self, event: DecisionEvent) -> None:
        if isinstance(event, PriorityCalculatedEvent):
            kind, node = "priority_calculated", event.parent
        else:
            kind = "high_score_links" if isinstance(event, HighScoreLinksEvent) else "low_score_links"
            node = event.node
        for record in event.records:
            self.decisions.append((event.seq, {
                "decision": kind, "seq": event.seq, "node_id": node.get_id(), **record,
            }))

    def wire_messages(self) -> list[dict[str, Any]]:
        return self.gateway.messages

    def link_scores(self) -> list[dict[str, Any]]:
        """Decisions in the order the broker emitted them (``seq``), not the order
        their handler tasks happened to run."""
        return [record for _, record in sorted(self.decisions, key=lambda item: item[0])]
