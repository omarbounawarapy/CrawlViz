"""Fast checks for the files a branch changed: lint plus the tests that cover them.

Used by `make check-changed` and by the agents' stop hook. "Changed" means anything
that differs from the merge base with main: committed, staged, unstaged or untracked.
The full suite still runs in `make check` and in CI.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "crawler-ui"
BASE_BRANCH = "main"
PYTHON_SUFFIXES = {".py"}
UI_SUFFIXES = {".js", ".jsx", ".ts", ".tsx"}


def _git(*args: str) -> list[str]:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return [line for line in result.stdout.splitlines() if line.strip()]


def changed_files(base: str) -> list[Path]:
    merge_base = _git("merge-base", "HEAD", base)
    names: set[str] = set()
    if merge_base:
        names.update(_git("diff", "--name-only", merge_base[0]))
    names.update(_git("diff", "--name-only"))
    names.update(_git("diff", "--name-only", "--cached"))
    names.update(_git("ls-files", "--others", "--exclude-standard"))
    return sorted(ROOT / name for name in names if (ROOT / name).is_file())


def python_tests_for(sources: list[Path]) -> list[Path]:
    """Test files that are changed themselves or import a changed module."""
    tests: set[Path] = set()
    modules = []
    for source in sources:
        relative = source.relative_to(ROOT)
        if relative.parts[0] == "tests" and relative.name.startswith("test_"):
            tests.add(source)
        elif relative.parts[0] != "tests":
            modules.append(".".join(relative.with_suffix("").parts).removesuffix(".__init__"))
    if modules:
        for test_file in (ROOT / "tests").rglob("test_*.py"):
            text = test_file.read_text(encoding="utf-8", errors="ignore")
            if any(module in text for module in modules):
                tests.add(test_file)
    return sorted(tests)


def run(command: list[str], cwd: Path) -> bool:
    print("$", " ".join(command), flush=True)
    return subprocess.run(command, cwd=cwd, check=False).returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE_BRANCH)
    args = parser.parse_args()

    files = changed_files(args.base)
    python_files = [path for path in files if path.suffix in PYTHON_SUFFIXES]
    ui_files = [path for path in files
                if path.suffix in UI_SUFFIXES and UI_DIR in path.parents
                and "node_modules" not in path.parts]
    if not python_files and not ui_files:
        print("check-changed: no Python or UI source changes")
        return 0

    ok = True
    if python_files:
        relative = [str(path.relative_to(ROOT)) for path in python_files]
        ok &= run(["uv", "run", "ruff", "check", *relative], ROOT)
        tests = python_tests_for(python_files)
        if tests:
            ok &= run(["uv", "run", "pytest", "-q", *[str(t.relative_to(ROOT)) for t in tests]],
                      ROOT)
    if ui_files:
        relative = [str(path.relative_to(UI_DIR)) for path in ui_files]
        ok &= run(["npx", "eslint", *relative], UI_DIR)
        ok &= run(["npx", "vitest", "related", "--run", "--passWithNoTests", *relative], UI_DIR)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
