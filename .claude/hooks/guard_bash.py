"""PreToolUse hook for Bash: the shell guardrails every agent shares.

Usage (agent frontmatter): python3 guard_bash.py --agent <name>
Rules come from the [bash] table in .claude/ownership.toml:
  - nobody pushes, force-updates, rebases, amends, resets hard or skips hooks;
  - only committers commit, and every commit title passes commit_msg_check;
  - nobody reads keys.json or .env files;
  - read-only agents do not change files from the shell;
  - only dependency managers add packages, only network agents call the network;
  - only pin updaters run pytest with --update-pins.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import block, load_ownership, read_hook_input  # noqa: E402
from commit_msg_check import check_title  # noqa: E402

FORBIDDEN_GIT = {
    r"\bgit\s+push\b": "pushing is Omar's call; report that the branch is ready instead",
    r"\bgit\b.*\s--force(-with-lease)?\b": "no force updates",
    r"\bgit\s+rebase\b": "no rebases; history after review only grows",
    r"\bgit\s+commit\b.*--amend\b": "no amends; add a new commit",
    r"\bgit\s+reset\s+--hard\b": "no hard resets; ask the lead",
    r"\bgit\s+filter-(branch|repo)\b": "no history rewrites",
    r"\bgit\s+config\b.*\buser\.(name|email)\b": "commit identity is Omar's and is not changed",
    r"--no-verify\b": "hooks are not skipped",
    r"\bgit\s+(checkout|switch)\s+(main|master)\b.*&&.*\bgit\s+merge\b": "only the lead merges",
}
SECRET_FILE = re.compile(r"(^|[\s/'\"=])(keys\.json[\w.-]*|\.env(\.[\w-]+)?)(\s|$|['\"])")
SECRET_SAFE_COMMANDS = {"chmod", "stat", "ls", "test", "["}
NETWORK_TOOLS = re.compile(r"(^|[\s;|&(])(curl|wget|nc|ncat|ssh|scp|rsync|http|httpie)\s")
DEPENDENCY_CHANGES = re.compile(
    r"\buv\s+(add|remove)\b|\bpip\s+install\b|\bnpm\s+(install|i|add|uninstall)\s+[^-\s]"
    r"|\bnpm\s+(update|upgrade)\b|\bnpx\s+npm-check-updates\b")
UPDATE_PINS = re.compile(r"--update-pins\b")
DESTRUCTIVE_RM = re.compile(r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+(?P<targets>.+)")
DANGEROUS_RM_TARGETS = {"/", "~", "..", ".", "*", ".git", "./", "../", "~/", "$HOME"}
WRITE_COMMANDS = re.compile(
    r"(^|[\s;|&(])(rm|mv|cp|touch|mkdir|tee|truncate|ln|chmod|chown|patch|dd)\s"
    r"|\bsed\s+(-[a-zA-Z]*i|--in-place)|\bgit\s+(add|commit|merge|checkout|switch|stash|restore"
    r"|apply|am|cherry-pick|revert|tag|branch\s+-[dD])\b|\b(uv\s+sync|npm\s+ci)\b")
REDIRECT_TARGET = re.compile(r"(?<![<>&\d])>{1,2}\s*(?P<target>[^\s;|&]+)")
TEMP_PREFIXES = ("/tmp/", "/dev/null", "/dev/stderr", "/dev/stdout")


def _commit_titles(command: str) -> list[str]:
    """Titles passed with git commit -m, so a bad title is caught before the commit."""
    titles = []
    for segment in re.split(r"&&|;|\|\|", command):
        if not re.search(r"\bgit\s+commit\b", segment):
            continue
        try:
            tokens = shlex.split(segment)
        except ValueError:
            continue
        for index, token in enumerate(tokens):
            if token in ("-m", "--message") and index + 1 < len(tokens):
                titles.append(tokens[index + 1].splitlines()[0])
            elif token.startswith("--message="):
                titles.append(token.split("=", 1)[1].splitlines()[0])
    return titles


def _check_git(agent: str, command: str, rules: dict) -> None:
    for pattern, reason in FORBIDDEN_GIT.items():
        if re.search(pattern, command):
            block(f"Blocked: {reason}.")
    if re.search(r"\bgit\s+commit\b", command):
        if agent not in rules["committers"]:
            block(f"{agent} does not commit. Report the change and the lead will route it.")
        if re.search(r"\s-m\s.*\s-m\s", command):
            block("Commit messages are title only: use a single -m.")
        for title in _commit_titles(command):
            problems = check_title(title)
            if problems:
                block("Commit title breaks the convention (AGENTS.md, commit conventions): "
                      + "; ".join(problems))


def _check_rm(command: str) -> None:
    match = DESTRUCTIVE_RM.search(command)
    if not match:
        return
    for target in match.group("targets").split():
        if target.startswith(("|", ";", "&")):
            break
        cleaned = target.strip("'\"").rstrip("/") or "/"
        if cleaned in DANGEROUS_RM_TARGETS or cleaned.startswith(("/home", "/etc", "/usr", "~")):
            block(f"Blocked: rm -r on {target!r}. Remove specific paths inside your area.")


def _check_readonly(command: str) -> None:
    if WRITE_COMMANDS.search(command):
        block("Read-only agent: this command changes files or git state. "
              "Report the finding instead.")
    for match in REDIRECT_TARGET.finditer(command):
        if not match.group("target").startswith(TEMP_PREFIXES):
            block("Read-only agent: redirect output to /tmp, not into the repository.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True)
    agent = parser.parse_args().agent

    command = read_hook_input().get("tool_input", {}).get("command", "")
    if not command:
        return
    rules = load_ownership()["bash"]

    _check_git(agent, command, rules)
    _check_rm(command)

    if SECRET_FILE.search(command):
        first_word = command.strip().split()[0]
        if first_word not in SECRET_SAFE_COMMANDS:
            block("Blocked: keys.json and .env files hold secrets and are never read by agents.")

    if DEPENDENCY_CHANGES.search(command) and agent not in rules["dependency_managers"]:
        block("Dependency changes go through platform-engineer: raise a CHANGE-REQUEST.")

    if UPDATE_PINS.search(command) and agent not in rules["pin_updaters"]:
        block("Pin goldens change only through test-engineer, with research-scientist sign-off.")

    if NETWORK_TOOLS.search(command) and agent not in rules["network"]:
        block(f"{agent} has no network access. Use the offline doubles, or ask the lead.")

    if agent in rules["readonly"]:
        _check_readonly(command)


if __name__ == "__main__":
    main()
