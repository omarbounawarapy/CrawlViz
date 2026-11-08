"""Filesystem roots a crawl reads and writes.

One frozen object instead of cwd-relative strings scattered across
pipelines, so a test (or a second deployment) can point a whole crawl at
a temporary directory with ``RuntimePaths.under(tmp_path)``.
"""

from dataclasses import dataclass
from pathlib import Path

from .config import (
    BASE_DIR,
    EXPORT_DIR_NAME,
    EXPORT_PATH,
    ITEMS_DB_NAME,
    ITEMS_DB_PATH,
    SPACE_STORE_DIR,
    TEMPLATES_DIR,
)

LOG_DIR_NAME = "logs"
DEBUG_DIR_NAME = "debug"
KEYS_FILE_NAME = "keys.json"
SETTINGS_FILE_NAME = "settings.json"
PRESETS_DIR_NAME = "presets"


@dataclass(frozen=True)
class RuntimePaths:
    items_db: Path = ITEMS_DB_PATH
    export_dir: Path = EXPORT_PATH
    log_dir: Path = BASE_DIR / LOG_DIR_NAME
    debug_dir: Path = BASE_DIR / DEBUG_DIR_NAME
    space_store_dir: Path = BASE_DIR / SPACE_STORE_DIR
    keys_file: Path = BASE_DIR / KEYS_FILE_NAME
    settings_file: Path = BASE_DIR / SETTINGS_FILE_NAME
    presets_dir: Path = BASE_DIR / PRESETS_DIR_NAME
    templates_dir: Path = TEMPLATES_DIR

    @classmethod
    def under(cls, root: Path, **overrides) -> "RuntimePaths":
        """Every writable root inside ``root``; ``templates_dir`` stays as
        the repo's unless overridden, since blueprints are read-only input."""
        root = Path(root)
        base = {
            "items_db": root / ITEMS_DB_NAME,
            "export_dir": root / EXPORT_DIR_NAME,
            "log_dir": root / LOG_DIR_NAME,
            "debug_dir": root / DEBUG_DIR_NAME,
            "space_store_dir": root / SPACE_STORE_DIR,
            "keys_file": root / KEYS_FILE_NAME,
            "settings_file": root / SETTINGS_FILE_NAME,
            "presets_dir": root / PRESETS_DIR_NAME,
        }
        return cls(**{**base, **overrides})


def default_runtime_paths() -> RuntimePaths:
    return RuntimePaths()
