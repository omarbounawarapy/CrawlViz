"""Puts ``src/`` on the import path until the package builds from it (ADR 1, Packaging).

Remove this file once ``pytest.ini`` lists ``src`` in ``pythonpath``.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
