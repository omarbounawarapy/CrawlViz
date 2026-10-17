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
OPEN_ENDED_BUDGET = 1000  # more requests than any test makes


def decision_records(url: str) -> list[dict[str, object]]:
    return [{"url": url, "score": 5, "nlp_score": 0.25}]


def high_score_event(seq: int, url: str) -> HighScoreLinksEvent:
    node = SimpleNamespace(get_id=lambda: NODE_ID)
    return HighScoreLinksEvent("1", node=node, links=[], records=decision_records(url), seq=seq)


async def test_it_listens_to_every_event_the_bridge_translates() -> None:
    observer = PinObserver(OPEN_ENDED_BUDGET)

    assert {
        HighScoreLinksEvent, LowScoreLinksEvent, PriorityCalculatedEvent, RequestStartedEvent,
        StopCrawlEvent,
    } <= set(observer.handlers)


async def test_each_decision_record_names_its_kind_and_node() -> None:
    observer = PinObserver(OPEN_ENDED_BUDGET)

    await observer.put(high_score_event(seq=3, url="u"))

    assert observer.link_scores() == [
        {"decision": "high_score_links", "seq": 3, "node_id": NODE_ID,
         "url": "u", "score": 5, "nlp_score": 0.25},
    ]


async def test_decisions_come_back_in_broker_order_whatever_order_they_arrived() -> None:
    observer = PinObserver(OPEN_ENDED_BUDGET)

    await observer.put(high_score_event(seq=2, url="second"))
    await observer.put(high_score_event(seq=1, url="first"))

    assert [record["url"] for record in observer.link_scores()] == ["first", "second"]


async def test_the_bridge_messages_for_the_events_are_kept() -> None:
    observer = PinObserver(OPEN_ENDED_BUDGET)

    await observer.put(StopCrawlEvent("NO_PROGRESS", 1, 0, 0.0))

    assert [message["type"] for message in observer.wire_messages()] == ["CRAWL_STOPPED"]


def request_started(node_id: str) -> RequestStartedEvent:
    return RequestStartedEvent("c", worker_id=0, node_id=node_id, url=f"https://x.test/{node_id}")


async def test_recording_closes_at_the_last_requested_page_but_the_stop_is_kept() -> None:
    observer = PinObserver(budget=2)

    await observer.put(high_score_event(seq=1, url="before"))
    await observer.put(request_started("1"))
    await observer.put(high_score_event(seq=2, url="before the last request"))
    await observer.put(request_started("2"))
    await observer.put(high_score_event(seq=3, url="after"))
    await observer.put(request_started("3"))
    await observer.put(StopCrawlEvent("NO_PROGRESS", 443, 4, 1.5))

    assert observer.closed
    scored = [record["url"] for record in observer.link_scores()]
    assert scored == ["before", "before the last request"]
    messages = observer.wire_messages()
    assert [message["type"] for message in messages].count("PIPELINE_EVENT") == 1
    assert messages[-1] == {"type": "CRAWL_STOPPED", "reason": "NO_PROGRESS"}
