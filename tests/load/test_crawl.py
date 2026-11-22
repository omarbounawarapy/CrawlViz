"""The load crawl reaches its page budget on the harness site, and fails loudly when it cannot.

These run a real ``Crawler`` on a small site, so each takes a few seconds.
"""

from pathlib import Path

import pytest

from tests.load.crawl import REACHED_PAGE_BUDGET, CrawlEndedEarlyError, LoadOptions, run_load_crawl

SMALL_SITE_PAGES = 30
CRAWL_TIMEOUT_SECONDS = 60.0
# Pages with fewer links than the cascade's percentile minimum (10) are bucketed by fixed
# cut-offs, which drop every link of the seed page on this site (see tests/load/site.py).
STARVING_OUT_DEGREE = 8


async def test_a_small_site_is_crawled_to_its_page_budget(tmp_path: Path) -> None:
    measurement = await run_load_crawl(SMALL_SITE_PAGES, tmp_path, CRAWL_TIMEOUT_SECONDS)

    assert measurement.stop_reason == REACHED_PAGE_BUDGET
    assert measurement.fetched_pages == SMALL_SITE_PAGES
    assert measurement.event_counts["PageFetchedEvent"] == SMALL_SITE_PAGES
    assert measurement.pages_per_second > 0
    assert measurement.loop_lag_samples > 0


async def test_a_site_that_runs_out_of_links_fails_with_the_stop_reason(tmp_path: Path) -> None:
    """Before the harness checked the stop reason, this crawl sat idle after its first page
    until the 600 s no-progress timeout and printed nothing. Now it ends as soon as the
    frontier is empty and nothing is in flight."""
    with pytest.raises(CrawlEndedEarlyError, match=r"FRONTIER_EXHAUSTED after \d+ of 30 pages"):
        await run_load_crawl(
            SMALL_SITE_PAGES,
            tmp_path,
            CRAWL_TIMEOUT_SECONDS,
            LoadOptions(out_degree=STARVING_OUT_DEGREE),
        )
