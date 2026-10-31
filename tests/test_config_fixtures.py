"""The config page's committed test fixtures are what the backend serves today.

`schema.json` is `GET /config/schema` and `defaults.json` is `GET /config/defaults`. They are
read through the route functions, so a change to `RuntimeConfig` that is not copied into the
fixtures fails here instead of leaving the UI tests green against a stale shape.
"""

import json
from pathlib import Path

import pytest

from routes.config import get_config_schema, get_defaults

FIXTURES = Path("crawler-ui/src/features/config/fixtures")
HOW_TO_REFRESH = (
    "the config fixtures are stale; save the output of the route function over the file, "
    "for example `python -c 'import json; from routes.config import get_defaults; "
    "print(json.dumps(get_defaults(), indent=2))'`, then run Prettier on it"
)


@pytest.mark.parametrize(
    ("fixture_name", "serve"),
    [("schema.json", get_config_schema), ("defaults.json", get_defaults)],
)
def test_committed_config_fixture_matches_the_backend(fixture_name, serve) -> None:
    committed = json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))
    # A JSON round trip makes both sides plain data (tuples become lists, as on the wire).
    assert json.loads(json.dumps(serve())) == committed, f"{fixture_name}: {HOW_TO_REFRESH}"
