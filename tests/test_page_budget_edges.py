"""The page budget holds where a fetch does not end in a page, and where the queue is bounded."""

import asyncio
from pathlib import Path
from typing import Any

from core.event_broker import EventBroker
from crawlviz.events import StopCrawlEvent
from crawlviz.shared import Domain, Node
from models import Storage
from pipelines import RetryStage
from pipelines.fetch_stage import FetchStage
from tests.synthetic_crawl import FETCH_WORKERS, CrawlOptions, build_synthetic_crawl

CRAWL_TIMEOUT_SECONDS = 60.0
BOUNDED_CRAWL_TIMEOUT_SECONDS = 30.0
PAGE_BUDGET = 200
SMALL_BUDGET = 3
SETTLE_SECONDS = 0.2
BOUNDED_FETCH_QUEUE = 8
RETRY_DELAY_SECONDS = 0.01
ROBOTS_TXT = "User-agent: *\nDisallow: /blocked/\n"
DOMAIN = Domain("t", "http://a.test", ".//a")


class ScriptedFetcher:
    """Serves a robots.txt that blocks ``/blocked/``, fails the first request of each URL in
    ``failing`` and answers the rest."""

    def __init__(self, failing: set[str] | None = None) -> None:
        self.failing = set(failing or ())
        self.answered: list[str] = []

    async def emit_request(self, params: dict[str, Any]) -> str:
        url: str = params["url"]
        if url.endswith("/robots.txt"):
            return ROBOTS_TXT
        if url in self.failing:
            self.failing.discard(url)
            raise ConnectionError("down")
        self.answered.append(url)
        return "<html></html>"

    async def close(self) -> None:
        pass


class HangingFetcher:
    """Never answers, so a fetch stays in flight until its worker is cancelled."""

    async def emit_request(self, params: dict[str, Any]) -> str:
        await asyncio.Event().wait()
        return ""

    async def close(self) -> None:
        pass


def _node(path: str, node_id: int, priority: float = 0.0) -> Node:
    return Node(node_id, url=f"http://a.test/{path}", domain=DOMAIN, priority=priority)


def _stage(
    fetcher: Any,
    page_budget: int,
    respect_robots: bool = False,
    broker: EventBroker | None = None,
) -> FetchStage:
    return FetchStage(
        broker or EventBroker(),
        max_concurrency=1,
        fetcher=fetcher,
        min_delay=0,
        jitter_max=0,
        respect_robots=respect_robots,
        page_budget=page_budget,
    )


async def test_a_crawl_with_a_bounded_fetch_queue_still_stops_at_its_budget(
    tmp_path: Path,
) -> None:
    """Workers waiting for a page held nodes, the bounded queue filled, the broker's handler
    blocked on it and the broker never reached the point where it stops the fetch stage. The
    grace is long here so that the crawl cannot end by the grace cancelling the stage."""
    crawl = build_synthetic_crawl(
        tmp_path,
        PAGE_BUDGET,
        CrawlOptions(
            fetch_queue_size=BOUNDED_FETCH_QUEUE, shutdown_grace_seconds=CRAWL_TIMEOUT_SECONDS
        ),
    )

    await asyncio.wait_for(crawl.crawler.start(), BOUNDED_CRAWL_TIMEOUT_SECONDS)

    assert crawl.watcher.stop_reason == "MAX_NODES_REACHED"
    assert crawl.fetched_pages == PAGE_BUDGET


async def test_pages_refused_by_robots_do_not_use_up_the_budget() -> None:
    fetcher = ScriptedFetcher()
    stage = _stage(fetcher, SMALL_BUDGET, respect_robots=True)
    blocked = [_node(f"blocked/{i}", 100 + i, priority=1.0) for i in range(SMALL_BUDGET)]
    allowed = [_node(f"p{i}", i) for i in range(SMALL_BUDGET + 1)]
    for node in [*blocked, *allowed]:
        await stage.queue.put(node)

    task = asyncio.create_task(stage.start())
    await asyncio.sleep(SETTLE_SECONDS)
    await asyncio.wait_for(stage.stop(), CRAWL_TIMEOUT_SECONDS)
    await asyncio.wait_for(task, CRAWL_TIMEOUT_SECONDS)

    assert len(fetcher.answered) == SMALL_BUDGET
    assert all("/blocked/" not in url for url in fetcher.answered)


async def test_a_page_the_retry_stage_requeues_is_fetched_within_the_budget() -> None:
    broker = EventBroker()
    fetcher = ScriptedFetcher(failing={"http://a.test/p0"})
    stage = _stage(fetcher, SMALL_BUDGET, broker=broker)
    retry = RetryStage(
        Storage(), broker, requests_pipeline=stage, retry_base_delay=RETRY_DELAY_SECONDS
    )
    broker.subscribe(stage, stage.event_types)
    broker.subscribe(retry, retry.event_types)
    tasks = [
        asyncio.create_task(broker.start()),
        asyncio.create_task(stage.start()),
        asyncio.create_task(retry.start()),
    ]
    # Only as many nodes as the budget: the failed one must be fetched again to fill it.
    for i in range(SMALL_BUDGET):
        await stage.queue.put(_node(f"p{i}", i))
    await asyncio.sleep(SETTLE_SECONDS * 2)
    await broker.emit(StopCrawlEvent("MANUAL_STOP", 0, 0, 0.0))
    await asyncio.wait_for(asyncio.gather(*tasks), CRAWL_TIMEOUT_SECONDS)

    assert len(fetcher.answered) == SMALL_BUDGET
    assert "http://a.test/p0" in fetcher.answered


async def test_a_cancelled_fetch_gives_its_page_back() -> None:
    stage = _stage(HangingFetcher(), page_budget=1)
    await stage.queue.put(_node("p0", 0))
    task = asyncio.create_task(stage.start())
    await asyncio.sleep(SETTLE_SECONDS)

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)

    assert not stage.budget_spent
    assert stage.pages_unclaimed == 1


STOP_AFTER_SECONDS = 1.0
LONG_BUDGET = 3000
# One fetch in flight per worker may finish after the stop, and a few more already claimed.
MOST_FETCHES_AFTER_A_STOP = 3 * FETCH_WORKERS


async def test_a_bounded_fetch_queue_stops_fetching_when_the_crawl_is_stopped(
    tmp_path: Path,
) -> None:
    """The fetch stage heard of the stop only at shutdown, behind dispatch tasks blocked on its
    full queue, and kept fetching meanwhile (135 requests after a stop; 8 with no bound)."""
    options = CrawlOptions(
        fetch_queue_size=BOUNDED_FETCH_QUEUE, shutdown_grace_seconds=CRAWL_TIMEOUT_SECONDS
    )
    crawl = build_synthetic_crawl(tmp_path, LONG_BUDGET, options)
    run = asyncio.create_task(crawl.crawler.start())
    await asyncio.sleep(STOP_AFTER_SECONDS)
    fetched_at_stop = crawl.fetched_pages

    assert await crawl.crawler.request_stop()
    await asyncio.wait_for(run, BOUNDED_CRAWL_TIMEOUT_SECONDS)

    assert crawl.watcher.stop_reason == "MANUAL_STOP"
    assert crawl.fetched_pages - fetched_at_stop <= MOST_FETCHES_AFTER_A_STOP
