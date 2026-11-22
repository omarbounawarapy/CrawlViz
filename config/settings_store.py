"""Persisted runtime settings.

Precedence, low to high: code defaults (config.py) < ``settings.json``
(edited from the UI) < per-run overrides sent with ``POST /run``.

Only the difference from the code defaults is written, so a default
changed in code still reaches every setting the user never touched.
Writes are atomic (temp file + rename).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from utils import save_json

from .redaction import sanitize_url, url_carries_credentials
from .runtime_config import RuntimeConfig, default_runtime_config

logger = logging.getLogger(__name__)


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
        if (
            isinstance(value, dict)
            and isinstance(base.get(key), dict)
            and key != "extra_headers"
            and not key.endswith("_weights")
            and key not in ("strategy_contexts", "endpoints")
        ):
            sub = diff(base[key], value)
            if sub:
                out[key] = sub
        elif base.get(key) != value:
            out[key] = value
    return out


def _drop_endpoint_credentials(stored: dict) -> list[str]:
    """Strip user info and credential-like queries from each stored provider endpoint, in
    place. Returns the names of the providers that were changed."""
    providers = stored.get("providers")
    endpoints = providers.get("endpoints") if isinstance(providers, dict) else None
    if not isinstance(endpoints, dict):
        return []
    cleaned: list[str] = []
    for name, url in endpoints.items():
        if isinstance(url, str) and url_carries_credentials(url):
            endpoints[name] = sanitize_url(url)
            cleaned.append(str(name))
    return cleaned


class SettingsFileError(Exception):
    """The stored settings file exists but cannot be read as a settings object."""


def read_stored(path: Path) -> dict:
    """The raw stored overrides: ``{}`` when no file exists yet.

    Raises ``SettingsFileError`` when the file exists but is unreadable or is not a
    JSON object, so a damaged file is never mistaken for "no settings".

    A provider endpoint saved with a user name, password or key (allowed before endpoints
    were checked) is cleaned here and the file is rewritten, so one old file cannot make
    every later load fail. The key belongs in the keys store.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise SettingsFileError(
            f"The settings file {path} could not be read ({exc.strerror or exc}). "
            "Check its permissions, or reset the settings from the Config page."
        ) from exc
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise SettingsFileError(
            f"The settings file {path} is not valid JSON ({exc}). "
            "Fix it by hand, or reset the settings from the Config page, "
            "which replaces it with the defaults."
        ) from exc
    if not isinstance(data, dict):
        raise SettingsFileError(
            f"The settings file {path} must hold a JSON object but holds "
            f"{type(data).__name__}. Fix it by hand, or reset the settings "
            "from the Config page, which replaces it with the defaults."
        )
    cleaned = _drop_endpoint_credentials(data)
    if cleaned:
        logger.warning(
            "Dropped the credential from the stored endpoint of provider(s) %r; "
            "keep the key in the keys store, not in the endpoint URL.",
            cleaned,
        )
        try:
            _write(Path(path), data)
        except OSError:
            logger.exception(
                "Could not rewrite the cleaned settings file; it still holds a credential."
            )
    return data


def _write(path: Path, data: dict) -> None:
    save_json(path, data, sort_keys=True)


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
    if section is None:
        stored = {}  # a full reset never reads the file, so it also repairs a damaged one
    else:
        stored = read_stored(settings_file)
        stored.pop(section, None)
    _write(settings_file, stored)
    return load_runtime_config(settings_file)
