"""The event counter hears every event type the crawl can emit, and only counts them."""

import asyncio

from core.event_broker import EventBroker
from crawlviz.events import PageFetchedEvent, StopCrawlEvent
from tests.load.event_counter import NO_STOP_REASON, EventCounter, all_event_types

BROKER_TIMEOUT_SECONDS = 5.0


def _stop_event() -> StopCrawlEvent:
    return StopCrawlEvent(
        reason="MAX_NODES_REACHED", node_count=3, max_depth=1, duration=0.5, detail=None
    )


def test_the_counter_listens_to_the_events_the_crawl_emits() -> None:
    types = all_event_types()

    assert StopCrawlEvent in types
    assert PageFetchedEvent in types
    assert len(types) == len(set(types))


async def test_counts_by_type_and_keeps_the_stop_reason() -> None:
    counter = EventCounter()
    broker = EventBroker()
    broker.subscribe(counter, counter.event_types)
    broker_task = asyncio.create_task(broker.start())

    await broker.emit(_stop_event())
    await asyncio.wait_for(broker_task, BROKER_TIMEOUT_SECONDS)

    assert counter.counts["StopCrawlEvent"] == 1
    assert counter.stop_reason == "MAX_NODES_REACHED"


def test_a_crawl_that_has_not_stopped_has_no_stop_reason() -> None:
    assert EventCounter().stop_reason == NO_STOP_REASON
