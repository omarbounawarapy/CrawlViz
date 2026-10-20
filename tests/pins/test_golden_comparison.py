"""How a run is compared with a golden file: floats within a rounding step, the rest exact."""
import json
import math
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
    golden = [{"nlp_breakdown": {"boilerplate_score": 0.534522}, "links": [{"priority": 0.6}]}]
    now = [{"nlp_breakdown": {"boilerplate_score": 0.534523}, "links": [{"priority": 0.599999}]}]

    assert failure_for(tmp_path, golden, now) is None


@pytest.mark.parametrize("difference", [1e-4, 2 * ROUNDING_STEP, -1e-4])
def test_a_float_further_away_fails(tmp_path: Path, difference: float) -> None:
    golden = [{"nlp_breakdown": {"target_similarity": 0.5}}]
    now = [{"nlp_breakdown": {"target_similarity": 0.5 + difference}}]

    failure = failure_for(tmp_path, golden, now)

    assert failure is not None and "record.nlp_breakdown.target_similarity" in failure


@pytest.mark.parametrize("key", ["temperature", "threshold", "weight"])
def test_a_float_that_is_not_a_computed_score_is_compared_exactly(
    tmp_path: Path, key: str
) -> None:
    failure = failure_for(tmp_path, [{key: 0.7}], [{key: 0.7 + ROUNDING_STEP}])

    assert failure is not None and f"record.{key}" in failure


@pytest.mark.parametrize("key", ["priority", "nlp_score"])
def test_the_computed_scores_may_differ_by_one_step(tmp_path: Path, key: str) -> None:
    assert failure_for(tmp_path, [{key: 0.7}], [{key: 0.7 + ROUNDING_STEP}]) is None


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
    golden = [{"n": 1, "priority": 0.5}, {"n": 2, "priority": 0.25}, {"n": 3, "priority": 0.75}]
    now = [
        {"n": 1, "priority": 0.5 + ROUNDING_STEP},
        {"n": 2, "priority": 0.3},
        {"n": 3, "priority": 0.75},
    ]

    failure = failure_for(tmp_path, golden, now)

    assert failure is not None
    assert "kind.jsonl changed (3 golden lines, 3 now)" in failure
    assert "line 2: record.priority: 0.25 became 0.3" in failure
    assert '-{"n": 2, "priority": 0.25}' in failure and '+{"n": 2, "priority": 0.3}' in failure
    assert "line 1" not in failure and '+{"n": 1' not in failure


def test_a_long_list_of_changed_values_is_cut_with_a_count(tmp_path: Path) -> None:
    golden: list[object] = [{"n": n, "x": 0.0} for n in range(MAX_CHANGED_VALUES + 5)]
    now: list[object] = [{"n": n, "x": 1.0} for n in range(MAX_CHANGED_VALUES + 5)]

    failure = failure_for(tmp_path, golden, now)

    assert failure is not None and "... 5 more values" in failure
    assert failure.count("became") == MAX_CHANGED_VALUES


def link(parent: int, nlp_score: float) -> dict[str, object]:
    """A `link_scores` record: the cascade's decision for a link found on page ``parent``."""
    return {"decision": "high_score_links", "node_id": parent, "nlp_score": nlp_score}


def candidates(parent: str, *scores: float) -> dict[str, object]:
    """A `CANDIDATE_EVALUATED` wire message: the scored links of one parent page."""
    return {
        "type": "CANDIDATE_EVALUATED",
        "parent_id": parent,
        "candidates": [{"nlp_score": score} for score in scores],
    }


LOW, HIGH = 0.5, 0.5 + ROUNDING_STEP


def test_two_priorities_that_swap_within_the_step_fail(tmp_path: Path) -> None:
    golden, now = [{"priority": LOW}, {"priority": HIGH}], [{"priority": HIGH}, {"priority": LOW}]

    failure = failure_for(tmp_path, golden, now)

    assert failure is not None and "order changed, priority" in failure
    assert '+{"priority": 0.500001}' in failure


def test_priorities_are_compared_across_parents(tmp_path: Path) -> None:
    golden = [{"parent_id": "1", "priority": LOW}, {"parent_id": "2", "priority": HIGH}]
    now = [{"parent_id": "1", "priority": HIGH}, {"parent_id": "2", "priority": LOW}]

    assert failure_for(tmp_path, golden, now) is not None


def test_two_scores_of_one_parent_that_swap_within_the_step_fail(tmp_path: Path) -> None:
    on_disk = failure_for(tmp_path, [link(7, LOW), link(7, HIGH)], [link(7, HIGH), link(7, LOW)])
    on_wire = failure_for(tmp_path, [candidates("7", LOW, HIGH)], [candidates("7", HIGH, LOW)])

    assert on_disk is not None and "order changed, nlp_score of parent 7" in on_disk
    assert on_wire is not None and "order changed, nlp_score of parent 7" in on_wire


def test_scores_of_different_parents_are_never_compared(tmp_path: Path) -> None:
    on_disk = failure_for(tmp_path, [link(7, LOW), link(8, HIGH)], [link(7, HIGH), link(8, LOW)])
    golden = [candidates("7", LOW), candidates("8", HIGH)]
    on_wire = failure_for(tmp_path, golden, [candidates("7", HIGH), candidates("8", LOW)])

    assert on_disk is None and on_wire is None


def test_a_score_with_no_parent_is_not_compared(tmp_path: Path) -> None:
    # NODE_SCORED_DETAIL names the scored node, not the page it was found on; the same
    # score is compared where its parent is named.
    golden = [{"node_id": "24", "nlp_score": LOW}, {"node_id": "25", "nlp_score": HIGH}]
    now = [{"node_id": "24", "nlp_score": HIGH}, {"node_id": "25", "nlp_score": LOW}]

    assert failure_for(tmp_path, golden, now) is None


def test_two_priorities_that_merge_on_one_rounded_value_pass(tmp_path: Path) -> None:
    # isi link_scores, seq 121 and 5: 0.234928 and 0.234929 are one float32 step apart.
    golden = [{"priority": 0.234928}, {"priority": 0.234929}]

    assert failure_for(tmp_path, golden, [{"priority": 0.234929}, {"priority": 0.234929}]) is None
    assert failure_for(tmp_path, golden, [{"priority": 0.234928}, {"priority": 0.234928}]) is None


def test_two_equal_priorities_that_split_by_a_step_pass(tmp_path: Path) -> None:
    golden, now = [{"priority": LOW}, {"priority": LOW}], [{"priority": LOW}, {"priority": HIGH}]

    assert failure_for(tmp_path, golden, now) is None


def test_a_long_list_of_order_violations_is_cut_with_a_count(tmp_path: Path) -> None:
    golden: list[object] = []
    now: list[object] = []
    for index in range(MAX_CHANGED_VALUES + 2):
        low = 0.1 + index * 1e-3
        golden += [{"priority": low}, {"priority": low + ROUNDING_STEP}]
        now += [{"priority": low + ROUNDING_STEP}, {"priority": low}]

    failure = failure_for(tmp_path, golden, now)

    assert failure is not None and "... 2 more order violations" in failure
    assert failure.count("order changed") == MAX_CHANGED_VALUES


def test_ordering_values_that_all_move_together_within_the_step_pass(tmp_path: Path) -> None:
    golden = [{"priority": 0.5}, {"priority": 0.5 + ROUNDING_STEP}, {"priority": 0.9}]
    now = [
        {"priority": 0.5 + ROUNDING_STEP},
        {"priority": 0.5 + 2 * ROUNDING_STEP},
        {"priority": 0.9},
    ]

    assert failure_for(tmp_path, golden, now) is None


def test_a_nan_matches_a_nan(tmp_path: Path) -> None:
    assert failure_for(tmp_path, [{"x": float("nan")}], [{"x": float("nan")}]) is None
    assert failure_for(tmp_path, [{"priority": math.nan}], [{"priority": math.nan}]) is None


def test_a_nan_does_not_match_a_number(tmp_path: Path) -> None:
    assert failure_for(tmp_path, [{"priority": math.nan}], [{"priority": 0.0}]) is not None
    assert failure_for(tmp_path, [{"priority": 0.0}], [{"priority": math.nan}]) is not None


def test_a_nan_priority_does_not_disturb_the_order_check(tmp_path: Path) -> None:
    # Sorting a list with a NaN in it leaves it unsorted, which read as an inversion.
    priorities = [0.3, 0.1, math.nan, 0.5, 0.7]
    drifting = {"nlp_breakdown": {"boilerplate_score": 0.534522}}
    golden = [drifting, *({"priority": value} for value in priorities)]
    now = [{"nlp_breakdown": {"boilerplate_score": 0.534523}}, *golden[1:]]

    assert failure_for(tmp_path, golden, now) is None


def test_negative_zero_matches_zero(tmp_path: Path) -> None:
    assert failure_for(tmp_path, [{"priority": 0.0}], [{"priority": -0.0}]) is None
    assert failure_for(tmp_path, [{"x": -0.0}], [{"x": 0.0}]) is None


def test_an_int_inside_nested_lists_is_not_a_float_and_the_failure_has_its_path(
    tmp_path: Path,
) -> None:
    failure = failure_for(tmp_path, [{"a": [[1, 2]]}], [{"a": [[1, 2.0]]}])

    assert failure is not None and "line 1: record.a[0][1]: 2 became 2.0" in failure


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
