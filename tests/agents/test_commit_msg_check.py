"""Commit titles follow the "<Area>: <outcome>" convention and are title only."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.agents.hook_runner import HOOKS

sys.path.insert(0, str(HOOKS))
from commit_msg_check import check_message, check_title  # noqa: E402


@pytest.mark.parametrize(
    "title",
    [
        "Fetch: rate limit holds across workers, per host",
        "Fetch: RequestsPipeline becomes FetchStage",
        "API: every route requires the session token",
        "Docs: README covers the model download",
        "Git: share the .claude team setup, keep personal settings ignored",
        "Docs: CLAUDE.md standards codes and AGENTS.md team workflow",
    ],
)
def test_titles_in_the_repo_convention_pass(title: str) -> None:
    assert check_title(title) == []


@pytest.mark.parametrize(
    "title",
    [
        "SEC-1 done",
        "Phase D: rename pipelines",
        "Config: W1 fixes",
        "Graph: step 3 of the plan",
        "Graph: Label placement moves",
        "Graph: label placement moves.",
        "fix stuff",
        "Graph: label placement moves \u2014 again",
        "Graph: label placement by Claude",
        "Docs: written with Anthropic tools",
    ],
)
def test_titles_outside_the_convention_fail(title: str) -> None:
    assert check_title(title) != []


def test_message_must_be_title_only() -> None:
    assert check_message("Graph: label placement moves\n") == []
    assert check_message("Graph: label placement moves\n\nCo-Authored-By: x\n") != []


def test_range_skips_merge_commits(tmp_path: Path) -> None:
    """GitHub's "Update branch" button writes "Merge branch 'main' into ...";
    a range check over a pull request must judge the authored commits only."""

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    git("commit", "-q", "--allow-empty", "-m", "Docs: the base commit")
    git("checkout", "-q", "-b", "feature")
    git("commit", "-q", "--allow-empty", "-m", "Fetch: the feature commit")
    git("checkout", "-q", "main")
    git("commit", "-q", "--allow-empty", "-m", "Docs: a later main commit")
    git("checkout", "-q", "feature")
    git("merge", "-q", "--no-ff", "-m", "Merge branch 'main' into feature", "main")

    result = subprocess.run(
        [sys.executable, str(HOOKS / "commit_msg_check.py"), "--range", "main..feature"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout
