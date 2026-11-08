"""The budget file loads, names the runs the harness uses, and judges a measurement."""

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from tests.load.budget import BUDGET_FILE, RunBudget, check_budget, load_budget
from tests.load.measurement import Measurement

LIMITS = RunBudget(
    max_wall_seconds=100,
    min_pages_per_second=10,
    max_peak_rss_mb=500,
    max_loop_lag_p99_ms=50,
    max_loop_lag_max_ms=200,
)
WITHIN_LIMITS = Measurement(
    page_budget=1000,
    fetched_pages=1001,
    wall_seconds=60.0,
    pages_per_second=16.7,
    peak_rss_mb=300.0,
    loop_lag_samples=6000,
    loop_lag_p50_ms=1.0,
    loop_lag_p99_ms=20.0,
    loop_lag_max_ms=90.0,
    stop_reason="MAX_NODES_REACHED",
    event_counts={"PageFetchedEvent": 1001},
)


def test_committed_budget_loads_and_has_the_runs_the_harness_uses() -> None:
    budget = load_budget()

    assert {"smoke", "full"} <= set(budget.runs)
    assert budget.status.strip()


def test_an_unknown_run_names_the_known_ones() -> None:
    with pytest.raises(KeyError, match="smoke"):
        load_budget().for_run("huge")


def test_a_mistyped_limit_is_refused(tmp_path: Path) -> None:
    data = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
    data["runs"]["smoke"]["max_wall_second"] = 5
    path = tmp_path / "budget.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValidationError, match="max_wall_second"):
        load_budget(path)


def test_a_newer_schema_is_refused(tmp_path: Path) -> None:
    data = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
    data["schema_version"] = 2
    path = tmp_path / "budget.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="schema_version"):
        load_budget(path)


def test_a_run_within_every_limit_has_no_problems() -> None:
    assert check_budget(WITHIN_LIMITS, LIMITS) == []


def test_a_run_exactly_on_a_limit_is_within_budget() -> None:
    on_the_line = dataclasses.replace(
        WITHIN_LIMITS,
        wall_seconds=LIMITS.max_wall_seconds,
        pages_per_second=LIMITS.min_pages_per_second,
        peak_rss_mb=LIMITS.max_peak_rss_mb,
        loop_lag_p99_ms=LIMITS.max_loop_lag_p99_ms,
        loop_lag_max_ms=LIMITS.max_loop_lag_max_ms,
    )

    assert check_budget(on_the_line, LIMITS) == []


@pytest.mark.parametrize(
    ("field", "value", "words"),
    [
        ("wall_seconds", 100.5, "wall time"),
        ("pages_per_second", 9.0, "pages/s"),
        ("peak_rss_mb", 501.0, "peak RSS"),
        ("loop_lag_p99_ms", 51.0, "lag p99"),
        ("loop_lag_max_ms", 201.0, "lag max"),
    ],
)
def test_each_limit_is_reported_by_name(field: str, value: float, words: str) -> None:
    changes: dict[str, Any] = {field: value}  # Any: dataclasses.replace takes every field type
    broken = dataclasses.replace(WITHIN_LIMITS, **changes)

    problems = check_budget(broken, LIMITS)

    assert len(problems) == 1
    assert words in problems[0]


def test_every_broken_limit_is_reported_not_just_the_first() -> None:
    broken = dataclasses.replace(WITHIN_LIMITS, wall_seconds=1000.0, peak_rss_mb=9000.0)

    assert len(check_budget(broken, LIMITS)) == 2
