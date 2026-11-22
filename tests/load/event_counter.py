"""Counts every event the crawl emits, by type, and remembers why the crawl stopped.

It subscribes to the broker the way a stage does (``event_types`` and ``put``), so it
needs no change to the crawler. It does no work beyond a dictionary increment, and holds
nothing but counts, so memory stays flat however long the run is.
"""

from collections import Counter

import crawlviz.events as crawl_events
from crawlviz.events import StopCrawlEvent

EVENT_TYPE_SUFFIX = "Event"
NO_STOP_REASON = "NOT_STOPPED"


def all_event_types() -> tuple[type, ...]:
    """Every event class the events package exports (names ending in ``Event``)."""
    exported = (getattr(crawl_events, name) for name in crawl_events.__all__)
    return tuple(
        item
        for item in exported
        if isinstance(item, type) and item.__name__.endswith(EVENT_TYPE_SUFFIX)
    )


class EventCounter:
    """A consumer of every event type. ``counts`` maps a type name to how many arrived."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()
        self.stop_reason = NO_STOP_REASON

    @property
    def event_types(self) -> tuple[type, ...]:
        return all_event_types()

    async def put(self, event: object) -> None:
        self.counts[type(event).__name__] += 1
        if isinstance(event, StopCrawlEvent):
            self.stop_reason = event.reason
