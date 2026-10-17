"""The pin observer: what it records from the events it hears."""
from types import SimpleNamespace

from pin_observer import PinObserver

from events import (
    HighScoreLinksEvent,
    LowScoreLinksEvent,
    PriorityCalculatedEvent,
    RequestStartedEvent,
    StopCrawlEvent,
)

NODE_ID = 7


def decision_records(url: str) -> list[dict[str, object]]:
    return [{"url": url, "score": 5, "nlp_score": 0.25}]


def high_score_event(seq: int, url: str) -> HighScoreLinksEvent:
    node = SimpleNamespace(get_id=lambda: NODE_ID)
    return HighScoreLinksEvent("1", node=node, links=[], records=decision_records(url), seq=seq)


async def test_it_listens_to_every_event_the_bridge_translates() -> None:
    observer = PinObserver()

    assert {
        HighScoreLinksEvent, LowScoreLinksEvent, PriorityCalculatedEvent, RequestStartedEvent,
        StopCrawlEvent,
    } <= set(observer.handlers)


async def test_each_decision_record_names_its_kind_and_node() -> None:
    observer = PinObserver()

    await observer.put(high_score_event(seq=3, url="u"))

    assert observer.link_scores() == [
        {"decision": "high_score_links", "seq": 3, "node_id": NODE_ID,
         "url": "u", "score": 5, "nlp_score": 0.25},
    ]


async def test_decisions_come_back_in_broker_order_whatever_order_they_arrived() -> None:
    observer = PinObserver()

    await observer.put(high_score_event(seq=2, url="second"))
    await observer.put(high_score_event(seq=1, url="first"))

    assert [record["url"] for record in observer.link_scores()] == ["first", "second"]


async def test_the_bridge_messages_for_the_events_are_kept() -> None:
    observer = PinObserver()

    await observer.put(StopCrawlEvent("NO_PROGRESS", 1, 0, 0.0))

    assert [message["type"] for message in observer.wire_messages()] == ["CRAWL_STOPPED"]
