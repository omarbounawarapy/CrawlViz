"""Commit titles follow the "<Area>: <outcome>" convention and are title only."""

from __future__ import annotations

import sys

import pytest

from tests.agents.hook_runner import HOOKS

sys.path.insert(0, str(HOOKS))
from commit_msg_check import check_message, check_title  # noqa: E402


@pytest.mark.parametrize("title", [
    "Fetch: rate limit holds across workers, per host",
    "Fetch: RequestsPipeline becomes FetchStage",
    "API: every route requires the session token",
    "Docs: README covers the model download",
])
def test_titles_in_the_repo_convention_pass(title: str) -> None:
    assert check_title(title) == []


@pytest.mark.parametrize("title", [
    "SEC-1 done", "Phase D: rename pipelines", "Config: W1 fixes", "Graph: step 3 of the plan",
    "Graph: Label placement moves", "Graph: label placement moves.", "fix stuff",
    "Graph: label placement moves \u2014 again", "Graph: label placement by Claude",
])
def test_titles_outside_the_convention_fail(title: str) -> None:
    assert check_title(title) != []


def test_message_must_be_title_only() -> None:
    assert check_message("Graph: label placement moves\n") == []
    assert check_message("Graph: label placement moves\n\nCo-Authored-By: x\n") != []
