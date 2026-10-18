"""Pin: a 50-page cascade crawl on the frozen ISI graph (benchmark/data/isi.json)."""
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest
from pin_crawl import run_pin_crawl
from pin_paths import REPO_ROOT

from benchmark.graph import FrozenGraph

ISI_GRAPH = REPO_ROOT / "benchmark" / "data" / "isi.json"
PIN = "isi"
PAGE_BUDGET = 50


async def test_isi_crawl_matches_its_golden_files(
    golden: Callable[[str, str, Iterable[object]], None],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = await run_pin_crawl(FrozenGraph.load(ISI_GRAPH), PAGE_BUDGET, tmp_path, monkeypatch)

    assert len(run.fetch_order) == PAGE_BUDGET
    golden(PIN, "fetch_order", run.fetch_order)
    golden(PIN, "link_scores", run.link_scores)
    golden(PIN, "llm_requests", run.llm_requests)
    golden(PIN, "wire_messages", run.wire_messages)
