"""Fixtures for the behaviour pins."""
from collections.abc import Callable, Iterable

import pytest
from golden_files import check_golden, golden_path
from pin_paths import PINS_DIR


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Every test in this folder is a pin: `pytest -m pins` selects them all."""
    for item in items:
        if PINS_DIR in item.path.parents:
            item.add_marker(pytest.mark.pins)


@pytest.fixture
def golden(update_pins: bool) -> Callable[[str, str, Iterable[object]], None]:
    """``golden(pin, kind, records)``: compare with, or under --update-pins rewrite,
    ``tests/pins/golden/<pin>/<kind>.jsonl``."""

    def check(pin: str, kind: str, records: Iterable[object]) -> None:
        check_golden(golden_path(pin, kind), records, update_pins)

    return check
