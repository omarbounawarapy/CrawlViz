"""PreToolUse hook for Edit, Write and NotebookEdit: keep each agent inside its area.

Usage (agent frontmatter): python3 guard_paths.py --agent <name>
The area comes from .claude/ownership.toml. A blocked edit tells the agent who owns
the path, so it can raise a CHANGE-REQUEST to the lead instead.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import (  # noqa: E402
    block, can_write, in_temp_root, is_method_file, owner_of, read_hook_input, repo_relative,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True)
    agent = parser.parse_args().agent

    payload = read_hook_input()
    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not file_path:
        return

    # Ownership rules apply inside any git work tree, including checkouts that live under
    # a temp folder; temp roots are only free scratch space outside repositories.
    rel_path = repo_relative(file_path, payload.get("cwd"))
    if rel_path is None:
        absolute = file_path if os.path.isabs(file_path) else os.path.join(
            payload.get("cwd") or os.getcwd(), file_path)
        if in_temp_root(absolute):
            return
        block(f"{file_path} is outside the repository and outside the temp roots; "
              f"{agent} may not write there.")
    if can_write(agent, rel_path):
        if is_method_file(rel_path) and agent != "research-scientist":
            print(f"Note: {rel_path} is a method file. List it in your report so the "
                  "research-scientist reviews the change.", file=sys.stderr)
        return

    owner = owner_of(rel_path) or "the lead (no owner listed)"
    block(f"{rel_path} is owned by {owner}, not {agent}. Do not edit it. Add a "
          f"CHANGE-REQUEST block to your report (to: {owner}, path, what, why, standard code) "
          "and the lead will route it.")


if __name__ == "__main__":
    main()
