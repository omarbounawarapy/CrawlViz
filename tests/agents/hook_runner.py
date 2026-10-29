"""Run the agent guard hooks the way Claude Code does: JSON on stdin, exit 2 blocks."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".claude" / "hooks"
BLOCKED = 2


def run_hook(script: str, payload: dict, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOKS / script), *args],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )


def edit(agent: str, rel_path: str) -> subprocess.CompletedProcess[str]:
    payload = {
        "tool_name": "Edit",
        "cwd": str(ROOT),
        "tool_input": {"file_path": str(ROOT / rel_path)},
    }
    return run_hook("guard_paths.py", payload, "--agent", agent)


def bash(agent: str, command: str) -> subprocess.CompletedProcess[str]:
    payload = {"tool_name": "Bash", "cwd": str(ROOT), "tool_input": {"command": command}}
    return run_hook("guard_bash.py", payload, "--agent", agent)
