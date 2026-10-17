"""Golden files for the behaviour pins: JSON lines, normalised so runs compare equal.

A golden file holds one JSON record per line, so a mismatch is reported as a
unified diff of lines: which fetch, which link, which message changed.

Values that change from run to run (timestamps, durations) are replaced by a
placeholder before anything is written or compared, and floats are rounded, so
a golden file is byte-identical across runs and across processes.
"""
import json
from collections.abc import Iterable

import numpy as np

# Keys whose value depends on the clock. The key stays in the record so a pin
# still notices when a message loses or gains one.
VOLATILE_KEYS = frozenset({"ts", "duration", "duration_ms"})
VOLATILE_PLACEHOLDER = "<volatile>"

# Decimal places kept for floats: far below any score difference that matters,
# far above float noise between numpy builds.
FLOAT_DECIMALS = 6


def normalise(value: object) -> object:
    """``value`` with volatile fields replaced and floats rounded, recursively.

    Takes JSON-like data (dict, list, str, int, float, bool, None). Numpy
    scalars and tuples are accepted and come back as plain Python values.
    """
    if isinstance(value, dict):
        return {
            str(key): VOLATILE_PLACEHOLDER if key in VOLATILE_KEYS else normalise(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [normalise(item) for item in value]
    if isinstance(value, float):
        return round(value, FLOAT_DECIMALS)
    if isinstance(value, np.generic):
        return normalise(value.item())
    return value


def render_lines(records: Iterable[object]) -> list[str]:
    """One compact, key-sorted JSON line per record."""
    return [
        json.dumps(normalise(record), sort_keys=True, ensure_ascii=False, separators=(", ", ": "))
        for record in records
    ]
