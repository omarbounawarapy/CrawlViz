"""``tests.load.run`` holds a run to its budget: the exit status and report say what broke."""

import dataclasses
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.load import run
from tests.load.budget import BUDGET_FILE, Budget, RunBudget
from tests.load.crawl import CrawlEndedEarlyError
from tests.load.measurement import Measurement

REPO_ROOT = Path(__file__).resolve().parents[2]
SMALL_RUN_PAGES = 30
SUBPROCESS_TIMEOUT_SECONDS = 120.0
IMPOSSIBLE_PAGES_PER_SECOND = 1_000_000

GOOD_MEASUREMENT = Measurement(
    page_budget=200,
    fetched_pages=201,
    wall_seconds=5.0,
    pages_per_second=40.2,
    peak_rss_mb=300.0,
    loop_lag_samples=500,
    loop_lag_p50_ms=0.5,
    loop_lag_p99_ms=5.0,
    loop_lag_max_ms=20.0,
    stop_reason="MAX_NODES_REACHED",
    event_counts={"PageFetchedEvent": 201},
)
LIMITS = RunBudget(
    max_wall_seconds=10,
    min_pages_per_second=10,
    max_peak_rss_mb=500,
    max_loop_lag_p99_ms=50,
    max_loop_lag_max_ms=100,
)


def _fake_crawl(monkeypatch: pytest.MonkeyPatch, outcome: Measurement | BaseException) -> None:
    """Replace the crawl with one that returns ``outcome`` or raises it."""

    async def crawl(*_args: object, **_kwargs: object) -> Measurement:
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(run, "run_load_crawl", crawl)
    monkeypatch.setattr(
        run,
        "load_budget",
        lambda _path: Budget(schema_version=1, status="test", runs={"smoke": LIMITS}),
    )


def _main(report: Path) -> int:
    return run.main(["--pages", "200", "--run", "smoke", "--report", str(report)])


def _read(report: Path) -> dict[str, Any]:  # Any: the JSON report
    data: dict[str, Any] = json.loads(report.read_text(encoding="utf-8"))
    return data


def test_a_run_within_budget_exits_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _fake_crawl(monkeypatch, GOOD_MEASUREMENT)

    assert _main(tmp_path / "report.json") == run.EXIT_WITHIN_BUDGET
    report = _read(tmp_path / "report.json")
    assert report["problems"] == []
    assert report["measurement"]["fetched_pages"] == 201


def test_a_run_over_budget_exits_one_and_names_the_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake_crawl(monkeypatch, dataclasses.replace(GOOD_MEASUREMENT, peak_rss_mb=900.0))

    assert _main(tmp_path / "report.json") == run.EXIT_OVER_BUDGET
    assert "peak RSS" in _read(tmp_path / "report.json")["problems"][0]
    assert "over budget" in capsys.readouterr().err


@pytest.mark.parametrize(
    "failure", [CrawlEndedEarlyError("stopped with NO_PROGRESS"), TimeoutError()]
)
def test_a_crawl_that_fails_exits_two_and_is_never_a_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: BaseException
) -> None:
    _fake_crawl(monkeypatch, failure)

    assert _main(tmp_path / "report.json") == run.EXIT_CRAWL_FAILED
    report = _read(tmp_path / "report.json")
    assert "crawl_failed" in report
    assert "measurement" not in report


def test_the_command_line_enforces_a_budget_on_a_real_crawl(tmp_path: Path) -> None:
    """End to end in a process of its own: a limit no crawl can meet makes the command fail."""
    budget = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
    budget["runs"]["smoke"]["min_pages_per_second"] = IMPOSSIBLE_PAGES_PER_SECOND
    budget_file = tmp_path / "budget.json"
    budget_file.write_text(json.dumps(budget), encoding="utf-8")
    report = tmp_path / "report.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.load.run",
            "--pages",
            str(SMALL_RUN_PAGES),
            "--run",
            "smoke",
            "--budget",
            str(budget_file),
            "--report",
            str(report),
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
        check=False,
    )

    assert result.returncode == run.EXIT_OVER_BUDGET, result.stderr
    assert "pages/s" in _read(report)["problems"][0]
