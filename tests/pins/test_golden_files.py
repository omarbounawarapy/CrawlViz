"""The golden-file helper: what it normalises, when it writes, how it fails."""

import numpy as np
from golden_files import (
    FLOAT_DECIMALS,
    VOLATILE_KEYS,
    VOLATILE_PLACEHOLDER,
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
