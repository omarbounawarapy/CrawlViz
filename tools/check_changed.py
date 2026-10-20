"""Fast checks for the files a branch changed: lint, types and the fast tests that cover them.

Used by `make check-changed` and by the agents' stop hook. "Changed" means anything
that differs from the merge base with main: committed, staged, unstaged or untracked.
The full suite still runs in `make check` and in CI.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "crawler-ui"
BASE_BRANCH = "main"
PYTHON_SUFFIXES = {".py"}
PYTEST_NO_TESTS_COLLECTED = 5
# A change to any of these can alter the result for every Python file, so the whole
# Python side is checked instead of only the changed files.
PYTHON_TOOLING_FILES = {
    "pyproject.toml", "pytest.ini", "uv.lock", "Makefile", ".github/workflows/ci.yml",
    ".claude/ownership.toml",  # decides which files count as method files
}
# The same glob matcher the guard hooks use, so the method file list has one source:
# [shared].method_files in .claude/ownership.toml.
HOOKS_COMMON = ROOT / ".claude" / "hooks" / "_common.py"
UI_SUFFIXES = {".js", ".jsx", ".ts", ".tsx"}


def _git(*args: str) -> list[str]:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return [line for line in result.stdout.splitlines() if line.strip()]


def _changed_names(*diff_args: str) -> set[str]:
    """Paths in a diff, including deleted files and the old side of renames."""
    names: set[str] = set()
    for line in _git("diff", "-M", "--name-status", *diff_args):
        _status, *paths = line.split("\t")
        names.update(paths)
    return names


def changed_files(base: str) -> list[Path]:
    """Changed paths. Deleted and renamed-away Python files stay in, so their importers run."""
    merge_base = _git("merge-base", "HEAD", base)
    if not merge_base:
        raise SystemExit(
            f"check-changed: no merge base between HEAD and '{base}'; "
            "committed changes cannot be listed (fetch it, or pass --base)"
        )
    names = _changed_names(merge_base[0])
    names.update(_changed_names())
    names.update(_changed_names("--cached"))
    names.update(_git("ls-files", "--others", "--exclude-standard"))
    kept = {name for name in names
            if (ROOT / name).is_file() or (name.endswith(".py") and not (ROOT / name).exists())}
    return sorted(ROOT / name for name in kept)


def python_modules() -> dict[str, Path]:
    """Dotted module name to file for every tracked or new Python file, packages by `__init__`."""
    names = _git("ls-files", "--cached", "--others", "--exclude-standard", "*.py")
    modules: dict[str, Path] = {}
    for name in names:
        if (ROOT / name).is_file():
            dotted = name.removesuffix(".py").replace("/", ".").removesuffix(".__init__")
            modules[dotted] = ROOT / name
    return modules


def _import_candidates(node: ast.AST, directory: tuple[str, ...]) -> set[str]:
    """Dotted names an import statement may refer to, including bare sibling imports."""
    if isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
    elif isinstance(node, ast.ImportFrom) and node.level:
        keep = len(directory) - (node.level - 1)
        prefix = ".".join(directory[:keep])
        module = ".".join(part for part in (prefix, node.module) if part)
        return {module, *(f"{module}.{alias.name}" for alias in node.names)}
    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""
        names = [module, *(f"{module}.{alias.name}" for alias in node.names)]
    else:
        return set()
    # pytest puts a test directory on sys.path, so `import sibling` works without a package.
    return {*names, *(f"{'.'.join(directory)}.{name}" for name in names)}


def import_names_of(path: Path) -> set[str]:
    """Dotted names `path` may import. Importing a.b.c also runs a and a.b, so those count."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    directory = path.relative_to(ROOT).parent.parts
    names: set[str] = set()
    for node in ast.walk(tree):
        for dotted in _import_candidates(node, directory):
            parts = dotted.split(".")
            names.update(".".join(parts[:end]) for end in range(1, len(parts) + 1))
    return names


def imports_of(path: Path, modules: dict[str, Path]) -> set[Path]:
    """Repo files that `path` imports."""
    found = {modules[name] for name in import_names_of(path) if name in modules}
    found.discard(path)
    return found


def dotted_name(path: Path) -> str:
    return path.relative_to(ROOT).with_suffix("").as_posix().replace("/", ".").removesuffix(
        ".__init__")


def python_tests_for(sources: list[Path]) -> list[Path]:
    """Test files that are changed, or import (transitively) a changed file.

    Static imports only: a module loaded through importlib or a string is not followed.
    A changed conftest.py selects every test beneath its directory.
    """
    modules = python_modules()
    importers: dict[Path, set[Path]] = {}
    for path in modules.values():
        for imported in imports_of(path, modules):
            importers.setdefault(imported, set()).add(path)
    reached: set[Path] = set()
    pending = list(sources)
    # A deleted or renamed-away file is in no module index: find its importers by name.
    removed = {dotted_name(source) for source in sources
               if source.suffix == ".py" and not source.exists()}
    if removed:
        pending.extend(path for path in modules.values() if removed & import_names_of(path))
    while pending:
        current = pending.pop()
        if current not in reached:
            reached.add(current)
            pending.extend(importers.get(current, ()))
    conftest_dirs = [source.parent for source in sources if source.name == "conftest.py"]
    return sorted(
        path for path in modules.values()
        if path.name.startswith("test_") and "tests" in path.relative_to(ROOT).parts
        and (path in reached or any(directory in path.parents for directory in conftest_dirs))
    )


def run(command: list[str], cwd: Path, accepted: tuple[int, ...] = (0,)) -> bool:
    print("$", " ".join(command), flush=True)
    return subprocess.run(command, cwd=cwd, check=False).returncode in accepted


def touches_method(files: list[Path]) -> bool:
    """True when a changed file can alter scores or visit order (the method files)."""
    spec = importlib.util.spec_from_file_location("guard_common", HOOKS_COMMON)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {HOOKS_COMMON}")
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    relative = [path.relative_to(ROOT).as_posix() for path in files]
    return any(common.is_method_file(name) for name in relative)


def check_python(python_files: list[Path], tooling_changed: bool) -> bool:
    # Deleted files have nothing to lint, but they still trigger mypy and their importers.
    relative = [str(path.relative_to(ROOT)) for path in python_files if path.exists()]
    ok = True
    if relative or tooling_changed:
        ok = run(["uv", "run", "ruff", "check", *([] if tooling_changed else relative)], ROOT)
    # mypy follows imports, so a change anywhere can break another module: always whole.
    ok &= run(["uv", "run", "mypy"], ROOT)
    tests = [] if tooling_changed else python_tests_for(python_files)
    if tests or tooling_changed:
        # Slow tests run in `make check` and CI; the stop hook has a 600 s limit.
        # Exit code 5 means every selected test was slow, which is not a failure.
        selected = [str(t.relative_to(ROOT)) for t in tests]
        ok &= run(["uv", "run", "pytest", "-q", "-m", "not slow", *selected],
                  ROOT, accepted=(0, PYTEST_NO_TESTS_COLLECTED))
    return ok


def check_ui(ui_files: list[Path]) -> bool:
    relative = [str(path.relative_to(UI_DIR)) for path in ui_files]
    ok = run(["npx", "eslint", *relative], UI_DIR)
    ok &= run(["npx", "vitest", "related", "--run", "--passWithNoTests", *relative], UI_DIR)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE_BRANCH)
    args = parser.parse_args()

    files = changed_files(args.base)
    python_files = [path for path in files if path.suffix in PYTHON_SUFFIXES]
    ui_files = [path for path in files
                if path.suffix in UI_SUFFIXES and UI_DIR in path.parents
                and "node_modules" not in path.parts]
    tooling_changed = any(path.relative_to(ROOT).as_posix() in PYTHON_TOOLING_FILES
                          for path in files)
    method_changed = touches_method(files)
    if not (python_files or ui_files or tooling_changed or method_changed):
        print("check-changed: no Python or UI source changes")
        return 0

    ok = True
    if python_files or tooling_changed:
        ok &= check_python(python_files, tooling_changed)
    if method_changed:
        # The method guards must hold even when slow: no `not slow` filter here.
        ok &= run(["uv", "run", "pytest", "-q", "-m", "pins or method_guard"], ROOT,
                  accepted=(0, PYTEST_NO_TESTS_COLLECTED))
    if ui_files:
        ok &= check_ui(ui_files)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
