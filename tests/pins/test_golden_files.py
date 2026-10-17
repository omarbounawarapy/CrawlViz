"""The golden-file helper: what it normalises, when it writes, how it fails."""
from pathlib import Path

import numpy as np
import pytest
from golden_files import (
    FLOAT_DECIMALS,
    MAX_DIFF_LINES,
    VOLATILE_KEYS,
    VOLATILE_PLACEHOLDER,
    check_golden,
    normalise,
    render_lines,
)


def test_volatile_fields_are_replaced_at_any_depth() -> None:
    record = {"type": "X", "ts": 1.5, "inner": [{"duration_ms": 9.0, "kept": 1}]}

    assert normalise(record) == {
        "type": "X",
        "ts": VOLATILE_PLACEHOLDER,
        "inner": [{"duration_ms": VOLATILE_PLACEHOLDER, "kept": 1}],
    }


def test_every_key_in_the_volatile_set_is_replaced() -> None:
    record = {key: 12.5 for key in VOLATILE_KEYS}

    assert normalise(record) == {key: VOLATILE_PLACEHOLDER for key in VOLATILE_KEYS}


def test_floats_are_rounded_so_noise_does_not_reach_the_file() -> None:
    assert normalise(0.1 + 0.2) == round(0.3, FLOAT_DECIMALS)
    assert normalise({"a": 1.23456789}) == {"a": 1.234568}


def test_numpy_scalars_become_plain_values() -> None:
    assert normalise({"a": np.float32(0.5), "b": np.int64(3)}) == {"a": 0.5, "b": 3}


def test_lines_are_sorted_compact_json_one_record_each() -> None:
    assert render_lines([{"b": 1, "a": "é"}, [1, 2]]) == ['{"a": "é", "b": 1}', "[1, 2]"]


def test_matching_records_pass_and_leave_the_file_alone(tmp_path: Path) -> None:
    path = tmp_path / "pin" / "kind.jsonl"
    assert check_golden(path, [{"a": 1}], update=True)
    stamp = path.stat().st_mtime_ns

    assert not check_golden(path, [{"a": 1}], update=False)
    assert not check_golden(path, [{"a": 1}], update=True)

    assert path.stat().st_mtime_ns == stamp


def test_update_creates_the_folder_and_rewrites_a_changed_file(tmp_path: Path) -> None:
    path = tmp_path / "pin" / "kind.jsonl"

    assert check_golden(path, [{"a": 1}], update=True)
    assert check_golden(path, [{"a": 2}], update=True)

    assert path.read_text(encoding="utf-8") == '{"a": 2}\n'


def test_a_difference_fails_with_a_diff_and_does_not_touch_the_file(tmp_path: Path) -> None:
    path = tmp_path / "kind.jsonl"
    check_golden(path, [{"page": "a"}, {"page": "b"}], update=True)

    with pytest.raises(AssertionError) as failure:
        check_golden(path, [{"page": "a"}, {"page": "c"}], update=False)

    message = str(failure.value)
    assert '-{"page": "b"}' in message and '+{"page": "c"}' in message
    assert path.read_text(encoding="utf-8") == '{"page": "a"}\n{"page": "b"}\n'


def test_a_missing_golden_file_fails_instead_of_being_created(tmp_path: Path) -> None:
    path = tmp_path / "kind.jsonl"

    with pytest.raises(AssertionError, match="--update-pins"):
        check_golden(path, [{"a": 1}], update=False)

    assert not path.exists()


def test_a_long_diff_is_cut_with_a_count_of_what_was_left_out(tmp_path: Path) -> None:
    path = tmp_path / "kind.jsonl"
    check_golden(path, [{"n": n} for n in range(200)], update=True)

    with pytest.raises(AssertionError) as failure:
        check_golden(path, [{"n": -n} for n in range(200)], update=False)

    assert "more diff lines" in str(failure.value)
    assert len(str(failure.value).splitlines()) <= MAX_DIFF_LINES + 3

