"""Persisted runtime settings.

Precedence, low to high: code defaults (config.py) < ``settings.json``
(edited from the UI) < per-run overrides sent with ``POST /run``.

Only the difference from the code defaults is written, so a default
changed in code still reaches every setting the user never touched.
Writes are atomic (temp file + rename).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .runtime_config import RuntimeConfig, default_runtime_config


def deep_merge(base: dict, over: dict) -> dict:
    """Recursive dict merge; non-dict values in `over` replace `base`."""
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def diff(base: dict, new: dict) -> dict:
    """The entries of `new` that differ from `base` (nested)."""
    out: dict[str, Any] = {}
    for key, value in new.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict) and key != "extra_headers" \
                and not key.endswith("_weights") \
                and key not in ("strategy_contexts", "endpoints"):
            sub = diff(base[key], value)
            if sub:
                out[key] = sub
        elif base.get(key) != value:
            out[key] = value
    return out


def read_stored(path: Path) -> dict:
    """The raw stored overrides, ``{}`` when the file is missing or invalid."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def load_runtime_config(
    settings_file: Path | None = None, overrides: dict | None = None
) -> RuntimeConfig:
    """Defaults + stored settings + `overrides`, validated.

    Raises ``pydantic.ValidationError`` when the merge is invalid."""
    merged = default_runtime_config().model_dump()
    if settings_file is not None:
        merged = deep_merge(merged, read_stored(settings_file))
    if overrides:
        merged = deep_merge(merged, overrides)
    return RuntimeConfig.model_validate(merged)


def save_settings(settings_file: Path, patch: dict) -> RuntimeConfig:
    """Merge `patch` into the stored settings and persist the difference
    from the defaults. Returns the new effective config; raises
    ``ValidationError`` (and writes nothing) when it is invalid."""
    defaults = default_runtime_config().model_dump()
    merged = deep_merge(deep_merge(defaults, read_stored(settings_file)), patch)
    cfg = RuntimeConfig.model_validate(merged)
    _write(settings_file, diff(defaults, cfg.model_dump()))
    return cfg


def replace_settings(settings_file: Path, full: dict) -> RuntimeConfig:
    """Replace the stored settings with `full` (a complete config)."""
    defaults = default_runtime_config().model_dump()
    cfg = RuntimeConfig.model_validate(deep_merge(defaults, full))
    _write(settings_file, diff(defaults, cfg.model_dump()))
    return cfg


def reset_settings(settings_file: Path, section: str | None = None) -> RuntimeConfig:
    """Drop one section's stored values, or all of them."""
    stored = read_stored(settings_file)
    if section is None:
        stored = {}
    else:
        stored.pop(section, None)
    _write(settings_file, stored)
    return load_runtime_config(settings_file)
