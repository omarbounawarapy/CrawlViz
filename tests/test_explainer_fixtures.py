"""The committed explainer fixtures are what the Python code produces today."""

import json

from tools import gen_explainer_fixtures as gen


def test_committed_fixtures_match_the_implementation():
    committed = json.loads(gen.OUT.read_text())
    assert json.loads(json.dumps(gen.build())) == committed, (
        "run `.venv/bin/python -m tools.gen_explainer_fixtures` and commit the result"
    )
