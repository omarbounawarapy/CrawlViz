"""What ends a crawl: only the stop controller's decision, never a stage that has nothing
to run."""

import asyncio
from pathlib import Path

import pytest

from core import Crawler
from tests.synthetic_crawl import CrawlOptions, build_synthetic_crawl

# Large enough that the crawl outlasts the short shutdown grace of the helper.
PAGE_BUDGET = 300
CRAWL_TIMEOUT_SECONDS = 60.0
REACHED_PAGE_BUDGET = "MAX_NODES_REACHED"
SHORT_GRACE = 0.1
SMALL_BUDGET = 30


async def test_a_crawl_without_the_debug_trace_runs_to_its_page_budget(tmp_path: Path) -> None:
    """The debug log sink returns from ``start()`` at once when it is off. The crawl took
    that for the end of the crawl, cancelled every stage after the shutdown grace and
    reported no stop reason."""
    crawl = build_synthetic_crawl(tmp_path, PAGE_BUDGET, CrawlOptions(debug_enabled=False))

    await asyncio.wait_for(crawl.crawler.start(), CRAWL_TIMEOUT_SECONDS)

    assert crawl.watcher.stop_reason == REACHED_PAGE_BUDGET
    assert crawl.fetched_pages >= PAGE_BUDGET


class _Probe:
    """Tasks for ``Crawler._run_until_stopped`` that record how they ended."""

    def __init__(self) -> None:
        self.release_broker = asyncio.Event()
        self.cancelled: list[str] = []

    async def broker(self) -> None:
        await self.release_broker.wait()

    async def quiet_stage(self) -> None:
        return None

    async def hung_stage(self, name: str) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.append(name)
            raise

    async def failing_stage(self) -> None:
        await asyncio.sleep(0)
        raise RuntimeError("a stage failed")


def _crawler() -> Crawler:
    return Crawler("wikiMD.json", llm=object(), fetcher=object())  # type: ignore[arg-type]


async def test_stages_still_running_are_cancelled_once_the_grace_is_over() -> None:
    probe = _Probe()
    run = asyncio.create_task(
        _crawler()._run_until_stopped(
            [probe.broker()],
            [probe.quiet_stage(), probe.hung_stage("straggler")],
            grace=SHORT_GRACE,
        )
    )
    await asyncio.sleep(SHORT_GRACE)
    assert not run.done(), "a stage that returned early ended the crawl"

    probe.release_broker.set()
    await asyncio.wait_for(run, CRAWL_TIMEOUT_SECONDS)

    assert probe.cancelled == ["straggler"]


async def test_a_stage_that_raises_ends_the_crawl_and_cancels_the_others() -> None:
    probe = _Probe()
    with pytest.raises(RuntimeError, match="a stage failed"):
        await asyncio.wait_for(
            _crawler()._run_until_stopped(
                [probe.broker()], [probe.failing_stage(), probe.hung_stage("bystander")], grace=60
            ),
            CRAWL_TIMEOUT_SECONDS,
        )

    assert probe.cancelled == ["bystander"]


# Fewer links per page than the scoring cascade's percentile minimum drops every link of the
# seed page on the synthetic site (see tests/load/site.py), so the frontier empties at once.
STARVING_OUT_DEGREE = 8
FRONTIER_EXHAUSTED = "FRONTIER_EXHAUSTED"
STARVED_CRAWL_TIMEOUT_SECONDS = 20.0


async def test_a_crawl_whose_frontier_runs_dry_stops_without_waiting_for_the_timeout(
    tmp_path: Path,
) -> None:
    """The crawl sat idle until the 60 s no-progress timeout (600 s by default)."""
    crawl = build_synthetic_crawl(
        tmp_path, SMALL_BUDGET, CrawlOptions(out_degree=STARVING_OUT_DEGREE)
    )

    await asyncio.wait_for(crawl.crawler.start(), STARVED_CRAWL_TIMEOUT_SECONDS)

    assert crawl.watcher.stop_reason == FRONTIER_EXHAUSTED
    assert 0 < crawl.fetched_pages < SMALL_BUDGET
