"""Commit message check: the repo's "<Area>: <outcome>" title convention, title only.

Usage:
  commit_msg_check.py <message-file>     # git commit-msg hook (lefthook)
  commit_msg_check.py --range A..B       # every commit in a range (CI)
  commit_msg_check.py --title "..."      # one title (used by guard_bash.py)

Exit code 1 when a message breaks the convention; the problems are printed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

MAX_TITLE_LENGTH = 120
TITLE_SHAPE = re.compile(r"^(?P<area>[A-Z][^:]{0,60}): (?P<summary>\S.*)$")
# A summary may start with a capital only when the first word is an identifier or
# acronym (FetchStage, API, LLM, CSV, README), not an ordinary capitalised word.
IDENTIFIER_START = re.compile(r"^(`|[A-Z]{2,}\b|[A-Z][a-z0-9]+[A-Z]|[A-Za-z_]+[._(]|\d)")
BANNED_PATTERNS = {
    r"\b(ARCH|CODE|NAME|PY|TS|HTML|CSS|A11Y|PERF|TEST|SEC|ETH|LLM|OBS|CONTRACT|UX|I18N"
    r"|REPRO|FAIR|DOC|GIT)-\d+\b": "standards codes belong in reviews, not commits",
    r"(?i)\bphase\s+[a-h0-9]\b": "phase labels describe the plan, not the change",
    r"\bW\d+\b": "workstream labels describe the plan, not the change",
    r"(?<![\w/])#\d+\b": "task numbers describe the plan, not the change",
    r"(?i)\bstep\s+\d+\b": "step numbers describe the plan, not the change",
    r"(?i)\b(wip|done|todo|plan|audit item)\b": "say what changed instead",
    # File names such as .claude/ and CLAUDE.md are fine; crediting the tool is not.
    r"(?i)(?<![./\w])(claude|anthropic)(?![./\w])"
    r"|\b(co-authored-by|generated with)\b": "no AI attribution",
    r"(?i)(^|\s)ai(\s|$)": "no AI attribution",
    "—": "no em dashes",
}


def check_title(title: str) -> list[str]:
    problems: list[str] = []
    match = TITLE_SHAPE.match(title)
    if not match:
        problems.append(
            'title must look like "<Area>: <what is now true or what changed>" '
            "with a capitalised area"
        )
    else:
        summary = match.group("summary")
        if summary[0].isupper() and not IDENTIFIER_START.match(summary):
            problems.append(
                "start the summary after the colon in lowercase (identifiers and acronyms are fine)"
            )
        if summary.endswith("."):
            problems.append("no trailing period")
    if len(title) > MAX_TITLE_LENGTH:
        problems.append(
            f"title is {len(title)} characters; keep it under {MAX_TITLE_LENGTH} (aim for about 72)"
        )
    for pattern, reason in BANNED_PATTERNS.items():
        if re.search(pattern, title):
            problems.append(reason)
    return problems


def check_message(message: str) -> list[str]:
    lines = [line for line in message.splitlines() if not line.startswith("#")]
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines or not lines[0].strip():
        return ["empty commit message"]
    problems = check_title(lines[0].strip())
    if any(line.strip() for line in lines[1:]):
        problems.append("title only: remove the body and any trailers")
    return problems


def _messages_in_range(revision_range: str) -> list[tuple[str, str]]:
    output = subprocess.run(
        ["git", "log", "--format=%H%x00%B%x1e", revision_range],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    commits = []
    for record in output.split("\x1e"):
        if record.strip():
            sha, _, body = record.strip().partition("\x00")
            commits.append((sha[:10], body))
    return commits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("message_file", nargs="?")
    parser.add_argument("--range", dest="revision_range")
    parser.add_argument("--title")
    args = parser.parse_args()

    if args.title is not None:
        results = [("title", check_title(args.title))]
    elif args.revision_range:
        results = [
            (sha, check_message(body)) for sha, body in _messages_in_range(args.revision_range)
        ]
    elif args.message_file:
        with open(args.message_file, encoding="utf-8") as handle:
            results = [("message", check_message(handle.read()))]
    else:
        parser.error("pass a message file, --range or --title")

    failed = False
    for label, problems in results:
        for problem in problems:
            failed = True
            print(f"{label}: {problem}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
