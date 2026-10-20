"""How a run is compared with a golden file: floats within a rounding step, the rest exact."""
import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from golden_files import FLOAT_DECIMALS, FLOAT_TOLERANCE, MAX_CHANGED_VALUES, check_golden
from pin_paths import PINS_DIR

ROUNDING_STEP = 10**-FLOAT_DECIMALS
CI_DRIFT_FIXTURE = PINS_DIR / "fixtures" / "ci_run_39410825053_wire_messages.json"


def failure_for(tmp_path: Path, golden: Sequence[object], now: Sequence[object]) -> str | None:
    """The failure message when ``now`` is compared with a golden file holding ``golden``."""
    path = tmp_path / "kind.jsonl"
    check_golden(path, golden, update=True)
    try:
        check_golden(path, now, update=False)
    except AssertionError as failure:
        return str(failure)
    return None


def test_the_tolerance_is_a_little_over_one_rounding_step() -> None:
    assert ROUNDING_STEP < FLOAT_TOLERANCE < 2 * ROUNDING_STEP


def test_a_float_one_rounding_step_away_passes_at_any_depth(tmp_path: Path) -> None:
    golden = [{"nlp_breakdown": {"boilerplate_score": 0.534522}, "candidates": [{"x": 0.633018}]}]
    now = [{"nlp_breakdown": {"boilerplate_score": 0.534523}, "candidates": [{"x": 0.633017}]}]

    assert failure_for(tmp_path, golden, now) is None


@pytest.mark.parametrize("difference", [1e-4, 2 * ROUNDING_STEP, -1e-4])
def test_a_float_further_away_fails(tmp_path: Path, difference: float) -> None:
    golden = [{"target_similarity": 0.5}]
    failure = failure_for(tmp_path, golden, [{"target_similarity": 0.5 + difference}])

    assert failure is not None and "record.target_similarity" in failure


@pytest.mark.parametrize(
    ("golden", "now"),
    [
        ({"node_id": "24"}, {"node_id": "25"}),
        ({"node_id": "24"}, {"node_id": 24}),
        ({"depth": 1}, {"depth": 2}),
        ({"depth": 1}, {"depth": 1.0}),
        ({"depth": 1}, {"depth": True}),
        ({"state": "CREATED"}, {"state": "CRAWLED"}),
        ({"llm_score": None}, {"llm_score": 0.0}),
        ({"a": 0.5}, {"a": 0.5, "extra": 1}),
        ({"a": 0.5, "b": 1}, {"a": 0.5}),
        ({"a": 0.5}, {"b": 0.5}),
        ({"a": [1, 2]}, {"a": [1, 2, 3]}),
        ({"a": [1, 2]}, {"a": [2, 1]}),
        ({"a": 0.5}, {"a": [0.5]}),
    ],
)
def test_anything_but_a_float_within_the_step_must_be_equal(
    tmp_path: Path, golden: dict[str, object], now: dict[str, object]
) -> None:
    assert failure_for(tmp_path, [golden], [now]) is not None


def test_the_order_of_the_records_is_part_of_the_golden(tmp_path: Path) -> None:
    pages = [{"page": "a"}, {"page": "b"}, {"page": "c"}]

    assert failure_for(tmp_path, pages, [pages[1], pages[0], pages[2]]) is not None
    assert failure_for(tmp_path, pages, pages[:2]) is not None


def test_the_failure_names_the_changed_values_and_leaves_out_the_tolerated_ones(
    tmp_path: Path,
) -> None:
    golden = [{"n": 1, "x": 0.5}, {"n": 2, "x": 0.25}, {"n": 3, "x": 0.75}]
    now = [{"n": 1, "x": 0.5 + ROUNDING_STEP}, {"n": 2, "x": 0.3}, {"n": 3, "x": 0.75}]

    failure = failure_for(tmp_path, golden, now)

    assert failure is not None
    assert "kind.jsonl changed (3 golden lines, 3 now)" in failure
    assert "line 2: record.x: 0.25 became 0.3" in failure
    assert '-{"n": 2, "x": 0.25}' in failure and '+{"n": 2, "x": 0.3}' in failure
    assert "line 1" not in failure and '+{"n": 1' not in failure


def test_a_long_list_of_changed_values_is_cut_with_a_count(tmp_path: Path) -> None:
    golden: list[object] = [{"n": n, "x": 0.0} for n in range(MAX_CHANGED_VALUES + 5)]
    now: list[object] = [{"n": n, "x": 1.0} for n in range(MAX_CHANGED_VALUES + 5)]

    failure = failure_for(tmp_path, golden, now)

    assert failure is not None and "... 5 more values" in failure
    assert failure.count("became") == MAX_CHANGED_VALUES


@pytest.mark.parametrize("key", ["priority", "nlp_score"])
def test_two_ordering_values_that_swap_within_the_step_fail(tmp_path: Path, key: str) -> None:
    golden = [{key: 0.5}, {key: 0.5 + ROUNDING_STEP}]
    now = [{key: 0.5 + ROUNDING_STEP}, {key: 0.5}]

    failure = failure_for(tmp_path, golden, now)

    assert failure is not None and f"order changed, {key}" in failure
    assert '+{"' + key + '": 0.500001}' in failure


def test_ordering_values_that_were_equal_or_apart_stay_so_or_fail(tmp_path: Path) -> None:
    equal = [{"priority": 0.5}, {"priority": 0.5}]
    apart = [{"priority": 0.5}, {"priority": 0.5 + ROUNDING_STEP}]

    assert failure_for(tmp_path, equal, [{"priority": 0.5}, {"priority": 0.5 + ROUNDING_STEP}])
    assert failure_for(tmp_path, apart, [{"priority": 0.5}, {"priority": 0.5}])


def test_ordering_values_that_all_move_together_within_the_step_pass(tmp_path: Path) -> None:
    golden = [{"priority": 0.5}, {"priority": 0.5 + ROUNDING_STEP}, {"priority": 0.9}]
    now = [
        {"priority": 0.5 + ROUNDING_STEP},
        {"priority": 0.5 + 2 * ROUNDING_STEP},
        {"priority": 0.9},
    ]

    assert failure_for(tmp_path, golden, now) is None


def test_the_same_run_fails_nothing_when_a_value_is_nan(tmp_path: Path) -> None:
    assert failure_for(tmp_path, [{"x": float("nan")}], [{"x": float("nan")}]) is None


def test_the_float_drift_seen_on_ci_passes(tmp_path: Path) -> None:
    """Run 39410825053 (Python 3.12, the runner's numpy) moved 7 wire messages by one
    rounding step in `nlp_breakdown`; the fixture holds those lines on both sides."""
    pairs = json.loads(CI_DRIFT_FIXTURE.read_text(encoding="utf-8"))
    golden = tmp_path / "wire_messages.jsonl"
    golden.write_text("".join(f"{pair['golden']}\n" for pair in pairs), encoding="utf-8")
    ci_records = [json.loads(pair["ci"]) for pair in pairs]

    assert len(pairs) == 7
    assert all(pair["golden"] != pair["ci"] for pair in pairs)
    assert not check_golden(golden, ci_records, update=False)
