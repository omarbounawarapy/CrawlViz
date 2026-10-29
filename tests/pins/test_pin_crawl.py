"""The pin crawl itself: offline, complete and repeatable, on a graph of a dozen pages."""

from pathlib import Path
from typing import Any

import pytest
from golden_files import render_lines
from pin_crawl import run_pin_crawl
from synthetic_site import build_site

from benchmark.graph import FrozenGraph

TOPIC = "diabetes insulin"
BRANCHES = 3
PAGE_BUDGET = 5
PASSIVITY_BUDGET = 10


def tree_graph() -> FrozenGraph:
    """Seed `s`, three children `a0..a2`, each with three leaves `a<i>l<j>`."""

    def page(name: str, targets: list[str]) -> dict[str, Any]:
        return {
            "label": 0,
            "title": name,
            "text": f"{name} insulin glucose",
            "links": [{"to": target, "anchor": f"{target} insulin"} for target in targets],
        }

    pages = {"s": page("s", [f"a{i}" for i in range(BRANCHES)])}
    for i in range(BRANCHES):
        leaves = [f"a{i}l{j}" for j in range(BRANCHES)]
        pages[f"a{i}"] = page(f"a{i}", leaves)
        pages.update({leaf: page(leaf, []) for leaf in leaves})
    return FrozenGraph(seed="s", pages=pages, topic=TOPIC)


async def test_a_pin_crawl_records_all_four_kinds_of_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = await run_pin_crawl(tree_graph(), PAGE_BUDGET, tmp_path, monkeypatch)

    assert run.fetch_order[0]["page"] == "s"
    assert len(run.fetch_order) == PAGE_BUDGET
    assert {record["decision"] for record in run.link_scores} >= {"priority_calculated"}
    assert run.llm_requests and all(request["prompt"] for request in run.llm_requests)
    assert {"NODE_ADDED", "NODE_EXPANDED", "CRAWL_STOPPED"} <= {
        message["type"] for message in run.wire_messages
    }


async def test_two_pin_crawls_give_byte_identical_golden_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = await run_pin_crawl(tree_graph(), PAGE_BUDGET, tmp_path / "first", monkeypatch)
    second = await run_pin_crawl(tree_graph(), PAGE_BUDGET, tmp_path / "second", monkeypatch)

    for kind in ("fetch_order", "link_scores", "llm_requests", "wire_messages"):
        assert render_lines(getattr(first, kind)) == render_lines(getattr(second, kind)), kind


async def test_the_observer_does_not_change_what_the_crawl_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = build_site()

    observed = await run_pin_crawl(site, PASSIVITY_BUDGET, tmp_path / "observed", monkeypatch)
    bare = await run_pin_crawl(
        site, PASSIVITY_BUDGET, tmp_path / "bare", monkeypatch, observed=False
    )

    assert observed.wire_messages and not bare.wire_messages  # the bare run really had no observer
    assert observed.fetch_order == bare.fetch_order
    assert observed.llm_requests == bare.llm_requests
