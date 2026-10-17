"""Pin: a cascade crawl on a seeded 200-page synthetic site generated in the test."""
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest
from pin_crawl import run_pin_crawl
from synthetic_site import PAGE_COUNT, build_site

PIN = "synthetic"
# Below the site size, and low enough that the cascade's dropped links do not
# leave the frontier empty before the budget is spent.
PAGE_BUDGET = 60


async def test_synthetic_crawl_matches_its_golden_files(
    golden: Callable[[str, str, Iterable[object]], None],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = await run_pin_crawl(build_site(), PAGE_BUDGET, tmp_path, monkeypatch)

    assert PAGE_BUDGET < PAGE_COUNT
    assert len(run.fetch_order) == PAGE_BUDGET
    golden(PIN, "fetch_order", run.fetch_order)
    golden(PIN, "link_scores", run.link_scores)
    golden(PIN, "llm_requests", run.llm_requests)
    golden(PIN, "wire_messages", run.wire_messages)
