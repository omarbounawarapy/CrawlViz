"""Fixtures for the behaviour pins."""

from collections.abc import Callable, Iterable
from pathlib import Path

import pytest
from golden_files import check_golden, describe_rewritten, golden_path
from pin_paths import PINS_DIR

# Golden files rewritten by this run, for the terminal summary.
rewritten: list[Path] = []


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Every test in this folder is a pin: `pytest -m pins` selects them all."""
    for item in items:
        if PINS_DIR in item.path.parents:
            item.add_marker(pytest.mark.pins)


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    """After an --update-pins run, say which golden files changed."""
    if not rewritten:
        return
    terminalreporter.write_sep("=", "golden files rewritten by --update-pins")
    for name in describe_rewritten(rewritten):
        terminalreporter.write_line(name)


@pytest.fixture
def golden(update_pins: bool) -> Callable[[str, str, Iterable[object]], None]:
    """``golden(pin, kind, records)``: compare with, or under --update-pins rewrite,
    ``tests/pins/golden/<pin>/<kind>.jsonl``."""

    def check(pin: str, kind: str, records: Iterable[object]) -> None:
        path = golden_path(pin, kind)
        if check_golden(path, records, update_pins):
            rewritten.append(path)

    return check
