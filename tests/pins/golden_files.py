"""Golden files for the behaviour pins: write them as JSON lines, compare, diff.

A golden file holds one JSON record per line, so a mismatch is reported as a
unified diff of lines: which fetch, which link, which message changed.

Values that change from run to run (timestamps, durations) are replaced by a
placeholder before anything is written or compared, and floats are rounded, so
a golden file is byte-identical across runs and across processes.

Comparing is structural: the golden file and the run are read back as JSON, and
everything must be equal except floats, which may differ by one rounding step
(see ``FLOAT_TOLERANCE``). A numpy or BLAS build that sums in another order moves
a value by about 1e-9, which lands on the other side of a rounding boundary now
and then. The order of every priority and NLP score must stay the same, so that
the tolerance cannot turn into a different crawl order.
"""
import difflib
import json
import math
from collections.abc import Iterable, Iterator
from itertools import pairwise
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

# Largest difference between a golden float and the same float now that still
# counts as equal: one rounding step, plus half a step so that the float error of
# subtracting two rounded values never decides. Two steps apart fails.
FLOAT_TOLERANCE = 1.5 * 10**-FLOAT_DECIMALS

# Keys whose floats decide the crawl order. Their values may drift within the
# tolerance, but their order may not. The queue compares any two priorities; the
# cascade compares NLP scores only among the links found on one parent page.
GLOBAL_ORDERING_KEYS = frozenset({"priority"})
PER_PARENT_ORDERING_KEYS = frozenset({"nlp_score"})

# Changed values listed in a failure message before "and N more".
MAX_CHANGED_VALUES = 10

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
    failure = explain_difference(path.name, expected, lines)
    if failure is not None:
        raise AssertionError(failure)
    return False


def floats_match(expected: float, actual: float) -> bool:
    return (
        expected == actual
        or abs(expected - actual) <= FLOAT_TOLERANCE
        or (math.isnan(expected) and math.isnan(actual))
    )


def changed_keys(
    expected: dict[str, object], actual: dict[str, object], path: str
) -> Iterator[str]:
    for key in sorted(expected.keys() | actual.keys()):
        child = f"{path}.{key}"
        if key not in actual:
            yield f"{child}: key removed"
        elif key not in expected:
            yield f"{child}: key added"
        else:
            yield from changed_values(expected[key], actual[key], child)


def changed_values(expected: object, actual: object, path: str) -> Iterator[str]:
    """One line per value that differs, named by its path (``path`` is the record's root).

    Floats within ``FLOAT_TOLERANCE`` match. Everything else must be equal, and
    of the same type: ``36`` is not ``36.0``.
    """
    if isinstance(expected, dict) and isinstance(actual, dict):
        yield from changed_keys(expected, actual, path)
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            yield f"{path}: {len(expected)} items became {len(actual)}"
        for index, (old, new) in enumerate(zip(expected, actual, strict=False)):
            yield from changed_values(old, new, f"{path}[{index}]")
    elif isinstance(expected, float) and isinstance(actual, float):
        if not floats_match(expected, actual):
            yield f"{path}: {expected!r} became {actual!r}"
    elif type(expected) is not type(actual) or expected != actual:
        yield f"{path}: {expected!r} became {actual!r}"


def parent_page_of(record: dict[str, object]) -> object:
    """The page whose links ``record`` is about, or None when it does not say.

    A `link_scores` record (it has a `decision`) names it as `node_id`; a wire
    message names it as `parent_id` (None for the seed page).
    """
    if "decision" in record:
        return record.get("node_id")
    return record.get("parent_id")


def collect_ordering_pairs(
    expected: object,
    actual: object,
    found: dict[str, list[tuple[float, float]]],
    parent: object = None,
) -> None:
    """Add ``(golden, now)`` for every float under an ordering key.

    Priorities go under "priority". An `nlp_score` goes under its parent page,
    the page it was found on, which a record or an enclosing record names; one that
    names no parent is not compared.
    """
    if isinstance(expected, dict) and isinstance(actual, dict):
        named = parent_page_of(expected)
        if named is not None:
            parent = named
        for key in expected.keys() & actual.keys():
            old, new = expected[key], actual[key]
            both_floats = isinstance(old, float) and isinstance(new, float)
            if both_floats and key in GLOBAL_ORDERING_KEYS:
                found.setdefault(key, []).append((old, new))
            elif both_floats and key in PER_PARENT_ORDERING_KEYS:
                if parent is not None:
                    found.setdefault(f"{key} of parent {parent}", []).append((old, new))
            else:
                collect_ordering_pairs(old, new, found, parent)
    elif isinstance(expected, list) and isinstance(actual, list):
        for old, new in zip(expected, actual, strict=False):
            collect_ordering_pairs(old, new, found, parent)


def ranking_violations(found: dict[str, list[tuple[float, float]]]) -> list[str]:
    """Where two values that were apart are now the other way round.

    Rounding is monotone: values that keep their true order can end up equal
    after rounding (a merge) or equal values can end up apart (a split), but never
    inverted. So only a strict inversion, golden ``a < b`` and now ``a > b``, is a
    different order. Comparing neighbours in golden order is enough to find one.
    """
    problems = []
    for label, pairs in sorted(found.items()):
        now_by_golden: dict[float, list[float]] = {}
        for golden, now in pairs:
            now_by_golden.setdefault(golden, []).append(now)
        for (low, low_now), (high, high_now) in pairwise(sorted(now_by_golden.items())):
            if max(low_now) > min(high_now):
                problems.append(
                    f"{label}: golden {low!r} < {high!r}, now {max(low_now)!r} > {min(high_now)!r}"
                )
    return problems


def cut_list(items: list[str], limit: int, what: str) -> list[str]:
    """The first ``limit`` items, then "... N more <what>" if there were more."""
    if len(items) <= limit:
        return items
    return [*items[:limit], f"... {len(items) - limit} more {what}"]


def compare_lines(expected: list[str], lines: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Compare equally long golden and current lines.

    Returns the changed values (one text each), the ordering violations, and the
    current lines with only the really changed ones kept: the rest are replaced
    by their golden line, so a diff of the two shows nothing else.
    """
    found: dict[str, list[tuple[float, float]]] = {}
    changed: list[str] = []
    kept = list(expected)
    for number, (old, new) in enumerate(zip(expected, lines, strict=True), start=1):
        old_record, new_record = json.loads(old), json.loads(new)
        collect_ordering_pairs(old_record, new_record, found)
        changes = [f"line {number}: {c}" for c in changed_values(old_record, new_record, "record")]
        if changes:
            kept[number - 1] = new
        changed += changes
    return changed, ranking_violations(found), kept


def explain_difference(name: str, expected: list[str], lines: list[str]) -> str | None:
    """None when ``lines`` match the golden ``expected`` lines, else the failure message.

    Lines that match only within the float tolerance are left out of the diff, so
    what it shows is what really changed (unless their order changed, then all show).
    """
    if expected == lines:
        return None
    details: list[str] = []
    shown = lines
    if len(expected) == len(lines):
        changed, violations, kept = compare_lines(expected, lines)
        if not changed and not violations:
            return None
        shown = lines if violations else kept
        order_lines = [f"order changed, {problem}" for problem in violations]
        details = [
            *cut_list(changed, MAX_CHANGED_VALUES, "values"),
            *cut_list(order_lines, MAX_CHANGED_VALUES, "order violations"),
        ]
    diff = list(
        difflib.unified_diff(
            expected, shown, fromfile=f"golden {name}", tofile="this run", lineterm="", n=1
        )
    )
    header = f"{name} changed ({len(expected)} golden lines, {len(lines)} now):"
    return "\n".join([header, *details, *cut_list(diff, MAX_DIFF_LINES, "diff lines")])


def describe_rewritten(paths: Iterable[Path]) -> list[str]:
    """Terminal-summary lines naming the rewritten golden files, relative to the golden folder."""
    return [str(path.relative_to(GOLDEN_DIR)) for path in sorted(set(paths))]
