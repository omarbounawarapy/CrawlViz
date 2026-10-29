"""Shared helpers for the agent guard hooks.

Hooks receive the tool call as JSON on stdin and block it by exiting with code 2,
in which case stderr is shown to the agent as the reason.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
import tomllib
from functools import cache
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
OWNERSHIP_FILE = HOOK_DIR.parent / "ownership.toml"
BLOCK_EXIT_CODE = 2


def read_hook_input() -> dict:
    raw = sys.stdin.read()
    return json.loads(raw) if raw.strip() else {}


def block(reason: str) -> None:
    print(reason, file=sys.stderr)
    sys.exit(BLOCK_EXIT_CODE)


@cache
def load_ownership() -> dict:
    with OWNERSHIP_FILE.open("rb") as handle:
        return tomllib.load(handle)


@cache
def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Translate a repo glob ("*" within a segment, "**" across segments) to a regex."""
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            parts.append(".*")
            index += 2
        elif pattern[index] == "*":
            parts.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            parts.append("[^/]")
            index += 1
        else:
            parts.append(re.escape(pattern[index]))
            index += 1
    return re.compile("".join(parts) + r"\Z")


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(_glob_regex(pattern).match(path) for pattern in patterns)


def _existing_ancestor(path: Path) -> Path:
    current = path
    while not current.exists() and current != current.parent:
        current = current.parent
    return current if current.is_dir() else current.parent


def repo_relative(file_path: str, cwd: str | None = None) -> str | None:
    """Return the path relative to the git work tree that contains it, or None.

    Works for the main checkout and for agent worktrees, and for files that do not
    exist yet (the nearest existing ancestor decides the work tree).
    """
    path = Path(file_path)
    if not path.is_absolute():
        path = Path(cwd or os.getcwd()) / path
    path = Path(os.path.normpath(path))
    anchor = _existing_ancestor(path)
    try:
        top = subprocess.run(
            ["git", "-C", str(anchor), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    try:
        return path.relative_to(Path(top).resolve()).as_posix()
    except ValueError:
        try:
            return path.resolve().relative_to(Path(top).resolve()).as_posix()
        except ValueError:
            return None


def agent_area(agent: str) -> tuple[list[str], list[str]]:
    config = load_ownership()["agents"].get(agent)
    if config is None:
        return [], []
    write = list(config.get("write", []))
    env_name = config.get("from_env")
    if env_name:
        write += [glob.strip() for glob in os.environ.get(env_name, "").split(",") if glob.strip()]
    return write, list(config.get("exclude", []))


def can_write(agent: str, rel_path: str) -> bool:
    # Agents with `memory:` keep notes under .claude/agent-memory*/<agent>/.
    if matches_any(
        rel_path, [f".claude/agent-memory/{agent}/**", f".claude/agent-memory-local/{agent}/**"]
    ):
        return True
    write, exclude = agent_area(agent)
    return matches_any(rel_path, write) and not matches_any(rel_path, exclude)


def owner_of(rel_path: str) -> str | None:
    for name in load_ownership()["agents"]:
        if name != "chore-runner" and can_write(name, rel_path):
            return name
    return None


def in_temp_root(absolute_path: str) -> bool:
    roots = load_ownership()["shared"]["temp_roots"]
    normalized = os.path.normpath(absolute_path)
    return any(
        fnmatch.fnmatch(normalized, root) or fnmatch.fnmatch(normalized, root + "/*")
        for root in roots
    )


def is_method_file(rel_path: str) -> bool:
    return matches_any(rel_path, load_ownership()["shared"]["method_files"])
