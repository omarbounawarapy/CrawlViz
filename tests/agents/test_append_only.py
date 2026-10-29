"""The benchmark protocol and the usability log never lose a line."""

from __future__ import annotations

from pathlib import Path

from tests.agents.hook_runner import BLOCKED, ROOT, run_hook


def test_append_only_rejects_removed_lines(tmp_path: Path) -> None:
    protocol = ROOT / "benchmark" / "PROTOCOL.md"
    remove = {
        "tool_name": "Edit",
        "cwd": str(ROOT),
        "tool_input": {
            "file_path": str(protocol),
            "old_string": "line one\nline two",
            "new_string": "line one",
        },
    }
    append = {
        "tool_name": "Edit",
        "cwd": str(ROOT),
        "tool_input": {
            "file_path": str(protocol),
            "old_string": "line one\nline two",
            "new_string": "line one\nline two\n\n## Amendment\nnew text",
        },
    }
    assert run_hook("append_only.py", remove).returncode == BLOCKED
    assert run_hook("append_only.py", append).returncode == 0


def test_append_only_ignores_other_files() -> None:
    payload = {
        "tool_name": "Edit",
        "cwd": str(ROOT),
        "tool_input": {
            "file_path": str(ROOT / "README.md"),
            "old_string": "a\nb",
            "new_string": "",
        },
    }
    assert run_hook("append_only.py", payload).returncode == 0
