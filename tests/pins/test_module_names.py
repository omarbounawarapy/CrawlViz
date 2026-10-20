"""No pins module can shadow a package or module the application imports.

`tests/pins` has no `__init__.py`, so pytest puts it on `sys.path` and its modules
import each other by bare name (`from golden_files import ...`); mypy does the same
through `mypy_path`. A pins module named `config.py` or `models.py` would then win
over the real top-level package and break imports silently. The rule is in
`README.md`; this test enforces it.
"""
import sys
from pathlib import Path

from pin_paths import PINS_DIR, REPO_ROOT

PYTHON_SUFFIX = ".py"
PACKAGE_MARKER = "__init__.py"


def get_importable_names(folder: Path) -> set[str]:
    """Names `import <name>` would find in `folder`: its .py files and its package folders."""
    names = {path.stem for path in folder.glob(f"*{PYTHON_SUFFIX}")}
    for child in folder.iterdir():
        has_python = child.is_dir() and any(child.glob(f"*{PYTHON_SUFFIX}"))
        if has_python or (child / PACKAGE_MARKER).exists():
            names.add(child.name)
    return names


def get_shadowing_names(pins_dir: Path, repo_root: Path) -> list[str]:
    """Pins module names that equal a repo-root name or a standard library module."""
    reserved = get_importable_names(repo_root) | set(sys.stdlib_module_names)
    return sorted(get_importable_names(pins_dir) & reserved)


def test_no_pins_module_shares_a_name_with_a_top_level_package_or_the_standard_library() -> None:
    assert get_shadowing_names(PINS_DIR, REPO_ROOT) == []


def test_the_check_finds_a_shadowing_module(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    pins_dir = repo_root / "tests" / "pins"
    (repo_root / "config").mkdir(parents=True)
    (repo_root / "config" / PACKAGE_MARKER).write_text("")
    (repo_root / "main.py").write_text("")
    pins_dir.mkdir(parents=True)
    for name in ("config.py", "main.py", "json.py", "golden_files.py"):
        (pins_dir / name).write_text("")

    assert get_shadowing_names(pins_dir, repo_root) == ["config", "json", "main"]
