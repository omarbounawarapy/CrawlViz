"""A crawl fetches at most its page budget, even when the stop decision comes late."""

import asyncio
from pathlib import Path
from typing import Any

from core.event_broker import EventBroker
from crawlviz.shared import Domain, Node
from pipelines.fetch_stage import FetchStage
from tests.synthetic_crawl import build_synthetic_crawl

CRAWL_TIMEOUT_SECONDS = 60.0
PAGE_BUDGET = 200
SMALL_BUDGET = 3
SETTLE_SECONDS = 0.2


async def test_a_crawl_on_a_site_that_answers_at_once_fetches_exactly_its_budget(
    tmp_path: Path,
) -> None:
    """The stop controller counted pages only after the events queued ahead of them, and an
    in-memory site was fetched 500 pages ahead of that count for a budget of 200."""
    crawl = build_synthetic_crawl(tmp_path, PAGE_BUDGET)

    await asyncio.wait_for(crawl.crawler.start(), CRAWL_TIMEOUT_SECONDS)

    assert crawl.fetched_pages == PAGE_BUDGET


class FlakyFetcher:
    """Fails the first request of every URL listed in ``failing`` and answers the rest."""

    def __init__(self, failing: set[str]) -> None:
        self.failing = set(failing)
        self.answered: list[str] = []

    async def emit_request(self, params: dict[str, Any]) -> str:
        url: str = params["url"]
        if url in self.failing:
            self.failing.discard(url)
            raise ConnectionError("down")
        self.answered.append(url)
        return "<html></html>"

    async def close(self) -> None:
        pass


def _node(node_id: int) -> Node:
    domain = Domain("t", "http://a.test", ".//a")
    return Node(node_id, url=f"http://a.test/p{node_id}", domain=domain)


def _stage(fetcher: FlakyFetcher, workers: int, page_budget: int | None) -> FetchStage:
    return FetchStage(
        EventBroker(),
        max_concurrency=workers,
        fetcher=fetcher,
        min_delay=0,
        jitter_max=0,
        page_budget=page_budget,
    )


async def _run_stage(stage: FetchStage, nodes: list[Node]) -> None:
    for node in nodes:
        await stage.queue.put(node)
    task = asyncio.create_task(stage.start())
    await asyncio.sleep(SETTLE_SECONDS)
    await asyncio.wait_for(stage.stop(), CRAWL_TIMEOUT_SECONDS)
    await asyncio.wait_for(task, CRAWL_TIMEOUT_SECONDS)


async def test_the_stage_fetches_no_more_pages_than_its_budget() -> None:
    fetcher = FlakyFetcher(failing=set())
    stage = _stage(fetcher, workers=2, page_budget=SMALL_BUDGET)

    await _run_stage(stage, [_node(i) for i in range(SMALL_BUDGET * 3)])

    assert len(fetcher.answered) == SMALL_BUDGET


async def test_a_failed_fetch_gives_its_page_back_to_the_budget() -> None:
    fetcher = FlakyFetcher(failing={"http://a.test/p0", "http://a.test/p1"})
    stage = _stage(fetcher, workers=1, page_budget=SMALL_BUDGET)

    await _run_stage(stage, [_node(i) for i in range(SMALL_BUDGET + 2)])

    assert len(fetcher.answered) == SMALL_BUDGET


async def test_a_stage_without_a_budget_fetches_every_node() -> None:
    fetcher = FlakyFetcher(failing=set())
    stage = _stage(fetcher, workers=2, page_budget=None)

    await _run_stage(stage, [_node(i) for i in range(SMALL_BUDGET * 3)])

    assert len(fetcher.answered) == SMALL_BUDGET * 3
