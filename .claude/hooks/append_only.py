"""PreToolUse hook for Edit and Write: append-only files never lose a line.

Applies to every agent (registered in .claude/settings.json). An edit may add text
anywhere, but every existing line must survive, in order.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import block, matches_any, read_hook_input, repo_relative  # noqa: E402

APPEND_ONLY = ["benchmark/PROTOCOL.md", "docs/usability-log.md"]


def _keeps_every_line(old: str, new: str) -> bool:
    remaining = iter(new.splitlines())
    return all(any(line == candidate for candidate in remaining) for line in old.splitlines())


def main() -> None:
    payload = read_hook_input()
    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path")
    if not file_path:
        return
    rel_path = repo_relative(file_path, payload.get("cwd"))
    if rel_path is None or not matches_any(rel_path, APPEND_ONLY):
        return

    if payload.get("tool_name") == "Edit":
        old, new = tool_input.get("old_string", ""), tool_input.get("new_string", "")
    else:
        try:
            with open(file_path, encoding="utf-8") as handle:
                old = handle.read()
        except FileNotFoundError:
            return
        new = tool_input.get("content", "")

    if not _keeps_every_line(old, new):
        block(
            f"{rel_path} is append-only: add an amendment below the existing text "
            "instead of changing or removing lines."
        )


if __name__ == "__main__":
    main()
