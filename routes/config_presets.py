"""Built-in and saved presets, and the goal guide's starting points."""

import json
import logging
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from config import settings_store as store
from config.runtime_config import default_runtime_config

from .config_support import ConfigPatch, get_paths, validation_http_error

logger = logging.getLogger(__name__)

router = APIRouter(tags=["config"])

BUILTIN_PRESETS: dict[str, dict[str, Any]] = {
    "polite": {
        "fetch": {"min_delay": 2.0, "jitter_max": 0.5},
        "pipelines": {"requests": {"workers": 2}},
    },
    "fast": {
        "fetch": {"min_delay": 0.2, "jitter_max": 0.05},
        "pipelines": {"requests": {"workers": 8}},
    },
    "frugal": {
        "scoring_cascade": {"high_score_llm_fraction": 0.1, "low_score_sample_fraction": 0.0},
    },
}


def _num(value: float) -> str:
    """A preset number as people read it: 2 not 2.0, 0.05 not 0.050000001."""
    return f"{value:g}"


def _pct(fraction: float) -> str:
    return f"{round(fraction * 100):g} %"


def _pace(values: dict[str, Any]) -> str:
    fetch = values["fetch"]
    workers = values["pipelines"]["requests"]["workers"]
    return (
        f"{_num(fetch['min_delay'])} s between requests "
        f"(plus up to {_num(fetch['jitter_max'])} s random) "
        f"and {workers} parallel fetches"
    )


# The built-in presets' names as people see them. The keys stay as they are (the API and the
# tests use them); the goal guide's cards use the same words, so a preset and its card match.
PRESET_LABELS: dict[str, str] = {
    "polite": "Gentler on a site",
    "fast": "Faster on a site that allows it",
    "frugal": "Cheaper",
}


def _preset_description(name: str, values: dict[str, Any]) -> str:
    """Prose generated from a preset's values, so the words cannot drift from the numbers."""
    if name == "polite":
        return f"Gentler on small sites: {_pace(values)}."
    if name == "fast":
        return f"Quicker crawl on sites that can take it: {_pace(values)}. More likely to see 429s."
    if name == "frugal":
        cascade = values["scoring_cascade"]
        base = default_runtime_config().scoring_cascade
        return (
            f"Spend less LLM budget: {_pct(cascade['high_score_llm_fraction'])} "
            f"of the high-confidence bucket goes to the model "
            f"(default {_pct(base.high_score_llm_fraction)}), and "
            f"{_pct(cascade['low_score_sample_fraction'])} of low-score links "
            f"are kept for exploration "
            f"(default {_pct(base.low_score_sample_fraction)})."
        )
    raise KeyError(name)


PRESET_DESCRIPTIONS: dict[str, str] = {
    name: _preset_description(name, values) for name, values in BUILTIN_PRESETS.items()
}

# The goal guide's three starting points. Each is a patch of settings, and its
# prose is generated from the same values, as the presets' prose is.
GOALS: dict[str, dict[str, Any]] = {
    "gentler": {
        "label": "Gentler on a site",
        "values": BUILTIN_PRESETS["polite"],
    },
    "cheaper": {
        "label": "Cheaper",
        "values": BUILTIN_PRESETS["frugal"],
    },
    "explore": {
        "label": "Explore more",
        "values": {
            "scoring_cascade": {
                "low_score_sample_fraction": 0.2,
                "default_priority_strategy": "exploration",
            },
            "priority": {"nlp_bias": 85, "llm_bias": 15},
        },
    },
}


def _goal_description(name: str, values: dict[str, Any]) -> str:
    if name == "gentler":
        return f"Waits longer between requests and fetches fewer pages at once: {_pace(values)}."
    if name == "cheaper":
        return _preset_description("frugal", values)
    if name == "explore":
        cascade = values["scoring_cascade"]
        priority = values["priority"]
        return (
            f"Keeps {_pct(cascade['low_score_sample_fraction'])} of doubtful links "
            f"for the LLM, orders the queue with the "
            f"{cascade['default_priority_strategy']} strategy, and weighs the NLP score "
            f"{_num(priority['nlp_bias'])} to the LLM's {_num(priority['llm_bias'])}."
        )
    raise KeyError(name)


def goals() -> dict[str, dict[str, Any]]:
    return {
        name: {
            "label": g["label"],
            "values": g["values"],
            "description": _goal_description(name, g["values"]),
        }
        for name, g in GOALS.items()
    }


_PRESET_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,39}$")


def _presets_file() -> Path:
    return get_paths().settings_file.with_name("presets.json")


def _read_presets() -> dict[str, Any]:
    try:
        data = json.loads(_presets_file().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.warning("could not read the saved presets from %s", _presets_file(), exc_info=True)
        return {}
    return data if isinstance(data, dict) else {}


def _check_preset_name(name: str) -> None:
    if name in BUILTIN_PRESETS or not _PRESET_NAME.match(name):
        raise HTTPException(status_code=422, detail=f"Invalid preset name '{name}'")


@router.get("/config/presets")
def list_presets() -> dict[str, Any]:
    return {
        "builtin": BUILTIN_PRESETS,
        "labels": PRESET_LABELS,
        "descriptions": PRESET_DESCRIPTIONS,
        "user": _read_presets(),
        "goals": goals(),
    }


@router.put("/config/presets/{name}")
def save_preset(name: str, body: ConfigPatch | None = None) -> dict[str, Any]:
    _check_preset_name(name)
    values = body.values if body and body.values else store.read_stored(get_paths().settings_file)
    try:
        store.load_runtime_config(None, values)
    except ValidationError as exc:
        raise validation_http_error(exc) from exc
    presets = _read_presets()
    presets[name] = values
    store._write(_presets_file(), presets)
    return {"saved": name}


@router.delete("/config/presets/{name}")
def delete_preset(name: str) -> dict[str, Any]:
    presets = _read_presets()
    if presets.pop(name, None) is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    store._write(_presets_file(), presets)
    return {"removed": name}


@router.post("/config/presets/{name}/apply")
def apply_preset(name: str) -> dict[str, Any]:
    values = BUILTIN_PRESETS.get(name) or _read_presets().get(name)
    if values is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    try:
        return store.replace_settings(get_paths().settings_file, values).model_dump()
    except ValidationError as exc:
        raise validation_http_error(exc) from exc
