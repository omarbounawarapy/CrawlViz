"""Golden files for the behaviour pins: write them as JSON lines, compare, diff.

A golden file holds one JSON record per line, so a mismatch is reported as a
unified diff of lines: which fetch, which link, which message changed.

Values that change from run to run (timestamps, durations) are replaced by a
placeholder before anything is written or compared, and floats are rounded, so
a golden file is byte-identical across runs and across processes.
"""
import difflib
import json
from collections.abc import Iterable
from pathlib import Path

import numpy as np
from pin_paths import PINS_DIR

GOLDEN_DIR = PINS_DIR / "golden"

# Keys whose value depends on the clock, or on which worker task won a race
# (`worker_id`). The key stays in the record so a pin still notices when a
# message loses or gains one.
VOLATILE_KEYS = frozenset(
    {"ts", "created_at", "start_time", "elapsed_seconds", "duration", "duration_ms", "worker_id"}
)
VOLATILE_PLACEHOLDER = "<volatile>"

# Decimal places kept for floats: far below any score difference that matters,
# far above float noise between numpy builds.
FLOAT_DECIMALS = 6

# Lines of diff shown in a failure message; the full diff would drown the
# runner's output when a whole pin changes.
MAX_DIFF_LINES = 60


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


def golden_path(pin: str, kind: str) -> Path:
    return GOLDEN_DIR / pin / f"{kind}.jsonl"


def check_golden(path: Path, records: Iterable[object], update: bool) -> bool:
    """Compare ``records`` with the golden file at ``path``.

    With ``update`` the file is rewritten instead (created with its folder if
    needed) and the result says whether its content changed. Without it, a
    missing file or any difference raises ``AssertionError`` carrying a unified
    diff, and the result is always False.
    """
    lines = render_lines(records)
    text = "".join(f"{line}\n" for line in lines)
    if update:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return False
        path.write_text(text, encoding="utf-8")
        return True
    if not path.exists():
        raise AssertionError(
            f"no golden file at {path}; create it deliberately with pytest -m pins --update-pins"
        )
    expected = path.read_text(encoding="utf-8").splitlines()
    if expected == lines:
        return False
    diff = list(
        difflib.unified_diff(
            expected, lines, fromfile=f"golden {path.name}", tofile="this run", lineterm="", n=1
        )
    )
    shown = diff[:MAX_DIFF_LINES]
    if len(diff) > MAX_DIFF_LINES:
        shown.append(f"... {len(diff) - MAX_DIFF_LINES} more diff lines")
    raise AssertionError(
        f"{path.name} changed ({len(expected)} golden lines, {len(lines)} now):\n"
        + "\n".join(shown)
    )


def describe_rewritten(paths: Iterable[Path]) -> list[str]:
    """Terminal-summary lines naming the rewritten golden files, relative to the golden folder."""
    return [str(path.relative_to(GOLDEN_DIR)) for path in sorted(set(paths))]
