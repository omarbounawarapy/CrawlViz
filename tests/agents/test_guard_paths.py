"""Each agent writes only inside its ownership area."""

from __future__ import annotations


import pytest

from tests.agents.hook_runner import BLOCKED, ROOT, edit, run_hook


@pytest.mark.parametrize(("agent", "path"), [
    ("backend-engineer", "pipelines/requests_pipeline.py"),
    ("backend-engineer", "tests/test_robots.py"),
    ("llm-engineer", "infrastructure/groq_translator.py"),
    ("frontend-engineer", "crawler-ui/src/features/graph/GraphView.jsx"),
    ("design-system-engineer", "crawler-ui/src/shared/theme/tokens.css"),
    ("research-scientist", "benchmark/analyze.py"),
    ("platform-engineer", "Makefile"),
    ("docs-writer", "docs/08-developer-guide.md"),
    ("test-engineer", "tests/pins/test_fetch_order.py"),
    ("ux-researcher", "docs/ux/requirements.md"),
    ("architect", "docs/adr/0001-package-layout.md"),
])
def test_owner_may_edit_own_area(agent: str, path: str) -> None:
    assert edit(agent, path).returncode == 0

@pytest.mark.parametrize(("agent", "path", "owner"), [
    ("frontend-engineer", "pipelines/requests_pipeline.py", "backend-engineer"),
    ("backend-engineer", "infrastructure/llm_handler.py", "llm-engineer"),
    ("backend-engineer", "crawler-ui/src/App.jsx", "frontend-engineer"),
    ("frontend-engineer", "crawler-ui/src/shared/theme/tokens.css", "design-system-engineer"),
    ("backend-engineer", "tests/pins/golden.json", "test-engineer"),
    ("docs-writer", "docs/adr/0001.md", "architect"),
    ("research-scientist", "benchmark/results/run.json", None),
    ("code-reviewer", "pipelines/robots.py", "backend-engineer"),
])
def test_edit_outside_area_is_blocked(agent: str, path: str, owner: str | None) -> None:
    result = edit(agent, path)
    assert result.returncode == BLOCKED
    if owner:
        assert owner in result.stderr

def test_temp_roots_are_writable_by_everyone() -> None:
    payload = {"tool_name": "Write", "cwd": str(ROOT),
               "tool_input": {"file_path": "/tmp/claude-1000/scratch/notes.md"}}
    assert run_hook("guard_paths.py", payload, "--agent", "code-reviewer").returncode == 0

def test_agents_may_write_their_own_memory_only() -> None:
    assert edit("code-reviewer", ".claude/agent-memory/code-reviewer/notes.md").returncode == 0
    assert edit("code-reviewer", ".claude/agent-memory/lead/notes.md").returncode == BLOCKED

def test_paths_outside_repo_are_blocked() -> None:
    payload = {"tool_name": "Write", "cwd": str(ROOT),
               "tool_input": {"file_path": "/home/someone/.bashrc"}}
    assert run_hook("guard_paths.py", payload, "--agent", "backend-engineer").returncode == BLOCKED

def test_chore_runner_area_comes_from_the_brief(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRAWLVIZ_CHORE_PATHS", "pipelines/**")
    assert edit("chore-runner", "pipelines/robots.py").returncode == 0
    assert edit("chore-runner", "routes/run.py").returncode == BLOCKED
