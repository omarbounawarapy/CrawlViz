"""Filesystem roots a crawl reads and writes.

One frozen object instead of cwd-relative strings scattered across
pipelines, so a test (or a second deployment) can point a whole crawl at
a temporary directory with ``RuntimePaths.under(tmp_path)``.
"""

from dataclasses import dataclass
from pathlib import Path

from .config import (
    BASE_DIR,
    EXPORT_PATH,
    ITEMS_DB_PATH,
    SPACE_STORE_DIR,
    TEMPLATES_DIR,
)


@dataclass(frozen=True)
class RuntimePaths:
    items_db: Path = ITEMS_DB_PATH
    export_dir: Path = EXPORT_PATH
    log_dir: Path = BASE_DIR / "logs"
    debug_dir: Path = BASE_DIR / "debug"
    space_store_dir: Path = BASE_DIR / SPACE_STORE_DIR
    keys_file: Path = BASE_DIR / "keys.json"
    templates_dir: Path = TEMPLATES_DIR

    @classmethod
    def under(cls, root: Path, **overrides) -> "RuntimePaths":
        """Every writable root inside ``root``; ``templates_dir`` stays as
        the repo's unless overridden, since blueprints are read-only input."""
        root = Path(root)
        base = {
            "items_db": root / "items.db",
            "export_dir": root / "export",
            "log_dir": root / "logs",
            "debug_dir": root / "debug",
            "space_store_dir": root / ".space_store",
            "keys_file": root / "keys.json",
        }
        return cls(**{**base, **overrides})


def default_runtime_paths() -> RuntimePaths:
    return RuntimePaths()
