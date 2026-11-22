"""The load runs the harness is for: a 200-page smoke in the normal suite, and the 50k run.

Each run is a process of its own (``python -m tests.load.run``), because peak memory is a
per-process maximum and the suite's own memory would be counted in it. The limits are the
committed ``budget.json``, so a run that gets slower or larger fails here.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.load.budget import load_budget
from tests.load.run import EXIT_WITHIN_BUDGET

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_PAGES = 200
FULL_PAGES = 50_000
# The harness enforces the run's own wall limit; this only stops a process that hangs.
SUBPROCESS_MARGIN_SECONDS = 120.0
FULL_RUN_ENV_VAR = "CRAWLVIZ_LOAD_FULL"


def _run_harness(run: str, pages: int, report: Path) -> dict[str, Any]:  # Any: the JSON report
    """Run the harness in a new process, require it to finish within budget, return its report."""
    timeout = load_budget().for_run(run).max_wall_seconds + SUBPROCESS_MARGIN_SECONDS
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.load.run",
            "--pages",
            str(pages),
            "--run",
            run,
            "--report",
            str(report),
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,  # the crawler's debug trace
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    assert result.returncode == EXIT_WITHIN_BUDGET, result.stderr
    report_data: dict[str, Any] = json.loads(report.read_text(encoding="utf-8"))
    return report_data


def test_a_200_page_smoke_crawl_is_within_budget(tmp_path: Path) -> None:
    report = _run_harness("smoke", SMOKE_PAGES, tmp_path / "smoke.json")

    measurement = report["measurement"]
    assert measurement["fetched_pages"] == SMOKE_PAGES
    assert measurement["stop_reason"] == "MAX_NODES_REACHED"
    assert measurement["event_counts"]["PageFetchedEvent"] == SMOKE_PAGES


@pytest.mark.slow
@pytest.mark.skipif(
    not os.environ.get(FULL_RUN_ENV_VAR),
    reason=f"hours-long run; set {FULL_RUN_ENV_VAR}=1 to run it",
)
@pytest.mark.timeout(
    int(load_budget().for_run("full").max_wall_seconds + SUBPROCESS_MARGIN_SECONDS * 2)
)
def test_a_50k_page_crawl_is_within_budget(tmp_path: Path) -> None:
    report = _run_harness("full", FULL_PAGES, tmp_path / "full.json")

    measurement = report["measurement"]
    assert measurement["fetched_pages"] >= FULL_PAGES
