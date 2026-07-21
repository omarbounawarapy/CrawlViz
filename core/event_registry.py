from collections import defaultdict
from collections.abc import Callable
from typing import Any


class EventRegistry:
    """Maps event types to the pipelines subscribed to them.

    Used internally by EventBroker; pipelines register interest via
    EventBroker.subscribe() rather than touching this directly.
    """

    def __init__(self):
        self.registry: dict[type[Any], list[Callable]] = defaultdict(list)

    def subscribe(self, pipeline, event_types: list[type[Any]]) -> None:
        """Register `pipeline` as a consumer of each event type in `event_types`."""
        for event_type in event_types:
            self.registry[event_type].append(pipeline)

    def event_consumers(self, event: Any) -> list[Callable]:
        """Return every pipeline subscribed to `event`'s type."""
        return self.registry[type(event)]

    def all_consumers(self) -> list[Any]:
        """Return every unique pipeline subscribed to *any* event type,
        in first-subscribed order. Used by EventBroker to broadcast
        shutdown to every pipeline once the crawl ends, regardless of
        whether that particular pipeline is individually subscribed to
        StopCrawlEvent -- see EventBroker._shutdown().
        """
        seen: set[int] = set()
        consumers: list[Any] = []
        for subscribers in self.registry.values():
            for consumer in subscribers:
                if id(consumer) not in seen:
                    seen.add(id(consumer))
                    consumers.append(consumer)
        return consumers
