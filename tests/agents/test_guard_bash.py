"""The shell guard blocks pushes, secrets, unowned dependency changes and writes by read-only agents."""

from __future__ import annotations

import pytest

from tests.agents.hook_runner import BLOCKED, bash


@pytest.mark.parametrize(
    "command",
    [
        "git push origin main",
        "git push",
        "git commit --amend -m 'Fetch: x'",
        "git rebase -i HEAD~3",
        "git reset --hard HEAD~1",
        "git config user.email bot@example.com",
        "git commit --no-verify -m 'Fetch: rate limit holds per host'",
        "cat keys.json",
        "cp keys.json /tmp/k",
        "head -1 .env",
        "rm -rf ~",
        "rm -rf .git",
        "uv add requests",
        "npm install left-pad",
        "curl https://example.org",
        "uv run pytest tests/pins --update-pins",
    ],
)
def test_forbidden_shell_commands_are_blocked(command: str) -> None:
    assert bash("backend-engineer", command).returncode == BLOCKED


@pytest.mark.parametrize(
    "command",
    [
        "uv run pytest -q tests/test_robots.py",
        "git status",
        "git diff --stat",
        "git commit -m 'Fetch: rate limit holds across workers, per host'",
        "chmod 600 keys.json",
        "rm -rf crawler-ui/dist",
        "npm ci",
    ],
)
def test_ordinary_builder_commands_pass(command: str) -> None:
    assert bash("backend-engineer", command).returncode == 0


def test_gatekeepers_do_not_commit_or_write() -> None:
    assert bash("code-reviewer", "git commit -m 'Fetch: x holds'").returncode == BLOCKED
    assert bash("code-reviewer", "sed -i 's/a/b/' main.py").returncode == BLOCKED
    assert bash("code-reviewer", "echo hi > notes.md").returncode == BLOCKED
    assert bash("code-reviewer", "git diff > /tmp/review.diff").returncode == 0
    assert bash("code-reviewer", "uv run pytest -q").returncode == 0


def test_platform_engineer_manages_dependencies() -> None:
    assert bash("platform-engineer", "uv add --dev hypothesis").returncode == 0


@pytest.mark.parametrize(
    "title",
    [
        "SEC-1 done",
        "Phase D: rename pipelines",
        "Fetch: Rate limit fixed",
        "Fetch: rate limit holds per host.",
        "Config: W1 fixes",
        "fetch: lowercase area",
    ],
)
def test_bad_commit_titles_are_blocked(title: str) -> None:
    assert bash("backend-engineer", f"git commit -m '{title}'").returncode == BLOCKED


def test_commit_body_is_blocked() -> None:
    command = "git commit -m 'Fetch: rate limit holds per host' -m 'details'"
    assert bash("backend-engineer", command).returncode == BLOCKED


def test_only_test_engineer_updates_pins() -> None:
    command = "uv run pytest -m pins --update-pins"
    assert bash("test-engineer", command).returncode == 0
    assert bash("backend-engineer", command).returncode == BLOCKED
