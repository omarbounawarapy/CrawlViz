"""Live application of the runtime settings flagged ``ui_apply: live``.

A running crawl owns its pipelines; ``apply_live`` writes the new value
onto the attribute each pipeline already reads per iteration (or, for
worker counts, calls the pipeline's ``resize``), so no queue is rebuilt.
Anything not listed in ``LIVE_BINDINGS`` is rejected rather than silently
ignored.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from config.runtime_config import RuntimeConfig
from config.settings_store import deep_merge

RESIZE = "@resize"

# dotted config path -> (pipeline key in Crawler._pipelines, attribute | RESIZE)
LIVE_BINDINGS: dict[str, tuple[str, str]] = {
    "fetch.min_delay": ("requests", "min_delay"),
    "fetch.jitter_max": ("requests", "jitter_max"),
    "fetch.backoff_max": ("requests", "max_backoff"),
    "retries.max_request_retries": ("retry", "max_request_retries"),
    "retries.max_scoring_retries": ("retry", "max_scoring_retries"),
    "pipelines.processing.workers": ("processing", RESIZE),
    "pipelines.requests.workers": ("requests", RESIZE),
    "pipelines.scoring.workers": ("scoring", RESIZE),
    "pipelines.storage.workers": ("storage", RESIZE),
    "pipelines.filtering.workers": ("filtering", RESIZE),
    "pipelines.priority.workers": ("priority", RESIZE),
    "pipelines.transformation.workers": ("transformation", RESIZE),
    "pipelines.debugging.workers": ("debug", RESIZE),
    "pipelines.retry.workers": ("retry", RESIZE),
}


def live_fields() -> set[str]:
    """Every dotted path the schema flags ``ui_apply: live``."""
    out: set[str] = set()

    def walk(model: type[BaseModel], prefix: str) -> None:
        for name, field in model.model_fields.items():
            path = f"{prefix}{name}"
            extra = field.json_schema_extra or {}
            if extra.get("ui_apply") == "live":
                out.add(path)
            inner = field.annotation
            if isinstance(inner, type) and issubclass(inner, BaseModel):
                walk(inner, path + ".")

    walk(RuntimeConfig, "")
    return out


class LiveSettingsError(ValueError):
    pass


def _flatten(patch: dict, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in patch.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict) and not any(
            b.startswith(path + ".") or b == path for b in LIVE_BINDINGS
        ):
            out[path] = value  # a non-live dict leaf; rejected below
        elif isinstance(value, dict):
            out.update(_flatten(value, path + "."))
        else:
            out[path] = value
    return out


def _lookup(config: RuntimeConfig, path: str) -> Any:
    value: Any = config
    for part in path.split("."):
        value = getattr(value, part)
    return value


def apply_live(config: RuntimeConfig, pipelines: dict, patch: dict) -> RuntimeConfig:
    """Validate `patch` on top of `config`, push the live fields onto
    `pipelines`, and return the new config. Raises ``LiveSettingsError``
    for a field that cannot change mid-run and ``ValidationError`` for an
    invalid value; nothing is applied in either case."""
    wanted = _flatten(patch)
    for path in wanted:
        if path not in LIVE_BINDINGS:
            raise LiveSettingsError(f"{path} cannot change during a run (applies next run)")

    new = RuntimeConfig.model_validate(deep_merge(config.model_dump(), patch))
    for path in wanted:
        pkey, attr = LIVE_BINDINGS[path]
        pipeline = pipelines.get(pkey)
        if pipeline is None:
            continue
        value = _lookup(new, path)
        if attr == RESIZE:
            pipeline.resize(value)
        else:
            setattr(pipeline, attr, value)
    return new
