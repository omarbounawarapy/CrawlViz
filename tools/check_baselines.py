"""Shrink-only guard for the mypy legacy list and the ruff per-file baseline.

Both baselines live in pyproject.toml. They record what was already wrong when a rule was
switched on; they may shrink but never grow. This script fails when:

* a module joins the mypy legacy list, or a code joins a ruff per-file entry, compared with
  the merge base with main (a rename shown by `git diff -M` in the same diff is not growth);
* an entry is stale: the module is strict-clean without it, or ruff no longer reports that
  code in that file (stale entries would silently hide future violations).

Used by `make check-baselines` and CI. The pure functions take in-memory inputs so tests
can call them directly.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_BRANCH = "main"
PYPROJECT = "pyproject.toml"
GLOB_CHARACTERS = "*?["
MYPY_ERROR_LINE = re.compile(r"^(?P<path>[^\s:]+\.py)(?::\d+)*: error")
SUCCESS_OR_FINDINGS = (0, 1)


@dataclass(frozen=True)
class Baselines:
    """What pyproject.toml lists: mypy legacy modules and ruff codes per file or glob."""

    mypy_modules: frozenset[str]
    ruff_codes: dict[str, frozenset[str]]


def parse_baselines(pyproject_text: str) -> Baselines:
    tool = tomllib.loads(pyproject_text).get("tool", {})
    modules: set[str] = set()
    for override in tool.get("mypy", {}).get("overrides", []):
        if override.get("ignore_errors") is True:
            listed = override.get("module", [])
            modules.update([listed] if isinstance(listed, str) else listed)
    per_file = tool.get("ruff", {}).get("lint", {}).get("per-file-ignores", {})
    return Baselines(
        frozenset(modules), {path: frozenset(codes) for path, codes in per_file.items()}
    )


def path_to_module(path: str) -> str:
    return path.removesuffix(".py").replace("/", ".").removesuffix(".__init__")


def is_glob(key: str) -> bool:
    return any(character in key for character in GLOB_CHARACTERS)


def find_additions(base: Baselines, current: Baselines, renames: dict[str, str]) -> list[str]:
    """Entries in `current` that `base` did not have, after following `git mv` renames."""
    module_renames = {path_to_module(old): path_to_module(new) for old, new in renames.items()}
    expected_modules = {module_renames.get(module, module) for module in base.mypy_modules}
    problems = [
        f"mypy legacy list gained {module}"
        for module in sorted(current.mypy_modules - expected_modules)
    ]
    expected_ruff = {renames.get(path, path): codes for path, codes in base.ruff_codes.items()}
    for path, codes in sorted(current.ruff_codes.items()):
        problems.extend(
            f"ruff baseline gained {code} for {path}"
            for code in sorted(codes - expected_ruff.get(path, frozenset()))
        )
    return problems


def find_stale_ruff(
    current: Baselines, violations: set[tuple[str, str]], existing_paths: set[str]
) -> list[str]:
    """Ruff entries for a file or code that is no longer violated. Globs are skipped."""
    problems = []
    for path, codes in sorted(current.ruff_codes.items()):
        if is_glob(path):
            continue
        if path not in existing_paths:
            problems.append(f"ruff baseline lists {path}, which does not exist")
            continue
        problems.extend(
            f"ruff baseline lists {code} for {path}, which no longer violates it"
            for code in sorted(codes)
            if (path, code) not in violations
        )
    return problems


def find_stale_mypy(current: Baselines, modules_with_errors: set[str]) -> list[str]:
    return [
        f"mypy legacy list names {module}, which is strict-clean or gone: remove it"
        for module in sorted(current.mypy_modules - modules_with_errors)
    ]


def parse_mypy_modules(output: str) -> set[str]:
    """Modules that have at least one error line in mypy's output."""
    modules = set()
    for line in output.splitlines():
        match = MYPY_ERROR_LINE.match(line)
        if match:
            modules.add(path_to_module(match.group("path")))
    return modules


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def read_renames(base_revision: str) -> dict[str, str]:
    """Old path to new path for files `git diff -M` shows renamed since the base."""
    renames = {}
    for line in _git("diff", "-M", "--name-status", "--diff-filter=R", base_revision).splitlines():
        _status, old, new = line.split("\t")[:3]
        renames[old] = new
    return renames


def _ruff_glob_override(globs: dict[str, frozenset[str]]) -> str:
    entries = []
    for key, codes in sorted(globs.items()):
        listed = ", ".join(json.dumps(code) for code in sorted(codes))
        entries.append(f"{json.dumps(key)} = [{listed}]")
    return "lint.per-file-ignores={" + ", ".join(entries) + "}"


def collect_ruff_violations(globs: dict[str, frozenset[str]]) -> set[tuple[str, str]]:
    """Every (path, code) ruff reports when only the glob ignores, not the baseline, apply."""
    result = subprocess.run(
        ["uv", "run", "ruff", "check", ".", "--output-format", "json",
         "--config", _ruff_glob_override(globs)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode not in SUCCESS_OR_FINDINGS:
        raise SystemExit(f"ruff failed: {result.stderr.strip()}")
    return {
        (Path(item["filename"]).relative_to(ROOT).as_posix(), item["code"])
        for item in json.loads(result.stdout)
    }


def collect_mypy_modules_without_baseline() -> set[str]:
    """Modules with mypy errors when the legacy list is not applied."""
    text = (ROOT / PYPROJECT).read_text(encoding="utf-8")
    # Config and cache live outside the repo; mypy resolves `files` and `mypy_path` against cwd.
    with tempfile.TemporaryDirectory() as scratch:
        config = Path(scratch) / "mypy-without-baseline.toml"
        config.write_text(text.replace("ignore_errors = true", "ignore_errors = false"),
                          encoding="utf-8")
        result = subprocess.run(
            ["uv", "run", "mypy", "--config-file", str(config),
             "--cache-dir", str(Path(scratch) / "cache")],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
    if result.returncode not in SUCCESS_OR_FINDINGS:
        raise SystemExit(f"mypy failed: {result.stdout}{result.stderr}")
    return parse_mypy_modules(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=BASE_BRANCH, help="branch to compare against")
    parser.add_argument("--skip-stale", action="store_true", help="only check for growth")
    args = parser.parse_args()

    current = parse_baselines((ROOT / PYPROJECT).read_text(encoding="utf-8"))
    base_revision = _git("merge-base", "HEAD", args.base).strip()
    base = parse_baselines(_git("show", f"{base_revision}:{PYPROJECT}"))
    problems: list[str] = []
    if base.mypy_modules or base.ruff_codes:
        problems = find_additions(base, current, read_renames(base_revision))
    else:
        print(f"check-baselines: {args.base} has no baselines yet; skipping the growth check")
    if not args.skip_stale:
        globs = {key: codes for key, codes in current.ruff_codes.items() if is_glob(key)}
        existing = {path for path in current.ruff_codes if (ROOT / path).exists()}
        problems += find_stale_ruff(current, collect_ruff_violations(globs), existing)
        problems += find_stale_mypy(current, collect_mypy_modules_without_baseline())
    for problem in problems:
        print(problem)
    if problems:
        print(f"check-baselines: {len(problems)} problem(s); baselines may only shrink")
        return 1
    checked = "did not grow" if args.skip_stale else "did not grow and have no stale entries"
    print(f"check-baselines: baselines {checked}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
