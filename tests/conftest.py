"""Options shared by the whole suite.

``--update-pins`` is the only way to rewrite the golden files under
``tests/pins/golden/``. It lives here, not in ``tests/pins/conftest.py``,
because pytest reads an option only from conftest files it loads at start-up,
and it does not load a ``pins`` sub-directory when the run starts at ``tests``.
"""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-pins",
        action="store_true",
        default=False,
        help="Rewrite the golden files of the behaviour pins instead of comparing with them.",
    )


@pytest.fixture
def update_pins(request: pytest.FixtureRequest) -> bool:
    """True when the run was started with ``--update-pins``."""
    return bool(request.config.getoption("--update-pins"))
