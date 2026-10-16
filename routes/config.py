"""
Config routes
=============
The runtime configuration (config/runtime_config.py) and the API keys,
readable and editable from the frontend.

GET  /config/schema     JSON Schema generated from the Pydantic model
GET  /config            values in effect (defaults + saved settings)
GET  /config/defaults   code defaults, for per-field reset
GET  /config/stored     only the values that differ from the defaults
PUT  /config            merge a partial config, validate, persist
PUT  /config/replace    replace the stored settings with a full config
POST /config/validate   validate a partial config without saving
POST /config/effective  saved settings with per-run overrides applied
GET  /config/export     the stored settings, for download
GET  /config/presets    built-in and saved presets
PUT  /config/presets/{name}          save a preset (body: values, or empty for the current settings)
POST /config/presets/{name}/apply    replace the settings with a preset
DELETE /config/presets/{name}
PATCH /config/live      change ui_apply=live fields of the running crawl
POST /config/reset      drop one section (?section=) or everything
POST /config/prompts/preview  the scoring prompt as the LLM receives it, from draft wording
GET  /config/providers  LLM providers and the models templates use
GET/POST/DELETE /keys   masked key management (full keys never returned)

Access: when CRAWLVIZ_API_TOKEN is set, every route here requires
``Authorization: Bearer <token>``. Unset, the API is open, which is only
acceptable bound to localhost.

Changes apply from the next crawl: pipelines copy their values at
construction. Fields flagged ``ui_apply: live`` can also be pushed to the
running crawl with PATCH /config/live (not persisted; PUT /config does that).
"""

import hmac
import json
import os
import re

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ValidationError

from config import RuntimePaths, default_runtime_paths
from config import settings_store as store
from config.runtime_config import RuntimeConfig, default_runtime_config
from core.live_settings import LiveSettingsError
from infrastructure.key_manager import KeyManager
from infrastructure.llm_handler import LlmHandler
from models.link import Link
from models.prompts import STRATEGIES, PromptBuilder

def _require_token(authorization: str | None = Header(default=None)) -> None:
    token = os.environ.get("CRAWLVIZ_API_TOKEN")
    if not token:
        return
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(status_code=401, detail="Missing or invalid API token")


router = APIRouter(tags=["config"], dependencies=[Depends(_require_token)])


def _paths() -> RuntimePaths:
    return default_runtime_paths()


def _errors(exc: ValidationError) -> list[dict]:
    return [
        {"path": ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
        for e in exc.errors()
    ]


def _422(exc: ValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail={"errors": _errors(exc)})


class ConfigPatch(BaseModel):
    values: dict


@router.get("/config/schema")
def get_config_schema() -> dict:
    """JSON Schema for RuntimeConfig, including the ui_* hints used by the
    frontend's generic schema-driven form renderer."""
    return RuntimeConfig.model_json_schema()


@router.get("/config")
def get_config() -> dict:
    """The runtime configuration currently in effect."""
    return store.load_runtime_config(_paths().settings_file).model_dump()


@router.get("/config/defaults")
def get_defaults() -> dict:
    return default_runtime_config().model_dump()


@router.get("/config/stored")
def get_stored() -> dict:
    return store.read_stored(_paths().settings_file)


@router.put("/config")
def put_config(body: ConfigPatch) -> dict:
    try:
        return store.save_settings(_paths().settings_file, body.values).model_dump()
    except ValidationError as exc:
        raise _422(exc)


@router.put("/config/replace")
def replace_config(body: ConfigPatch) -> dict:
    try:
        return store.replace_settings(_paths().settings_file, body.values).model_dump()
    except ValidationError as exc:
        raise _422(exc)


@router.post("/config/validate")
def validate_config(body: ConfigPatch) -> dict:
    try:
        store.load_runtime_config(_paths().settings_file, body.values)
    except ValidationError as exc:
        return {"valid": False, "errors": _errors(exc)}
    return {"valid": True, "errors": []}


@router.post("/config/effective")
def effective_config(body: ConfigPatch) -> dict:
    try:
        return store.load_runtime_config(_paths().settings_file, body.values).model_dump()
    except ValidationError as exc:
        raise _422(exc)


@router.patch("/config/live")
def patch_live(body: ConfigPatch) -> dict:
    from routes import run as run_routes

    crawler = run_routes._current_crawler
    if crawler is None:
        raise HTTPException(status_code=409, detail="No active crawl")
    try:
        return crawler.apply_live(body.values).model_dump()
    except ValidationError as exc:
        raise _422(exc)
    except LiveSettingsError as exc:
        raise HTTPException(status_code=422, detail={"errors": [{"path": "", "message": str(exc)}]})


@router.post("/config/reset")
def reset_config(section: str | None = None) -> dict:
    if section is not None and section not in RuntimeConfig.model_fields:
        raise HTTPException(status_code=404, detail=f"Unknown section '{section}'")
    return store.reset_settings(_paths().settings_file, section).model_dump()


BUILTIN_PRESETS: dict[str, dict] = {
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


def _pace(values: dict) -> str:
    fetch = values["fetch"]
    workers = values["pipelines"]["requests"]["workers"]
    return (f"{_num(fetch['min_delay'])} s between requests (plus up to {_num(fetch['jitter_max'])} s random) "
            f"and {workers} parallel fetches")


# The built-in presets' names as people see them. The keys stay as they are (the API and the
# tests use them); the goal guide's cards use the same words, so a preset and its card match.
PRESET_LABELS: dict[str, str] = {
    "polite": "Gentler on a site",
    "fast": "Faster on a site that allows it",
    "frugal": "Cheaper",
}


def _preset_description(name: str, values: dict) -> str:
    """Prose generated from a preset's values, so the words cannot drift from the numbers."""
    if name == "polite":
        return f"Gentler on small sites: {_pace(values)}."
    if name == "fast":
        return f"Quicker crawl on sites that can take it: {_pace(values)}. More likely to see 429s."
    if name == "frugal":
        cascade = values["scoring_cascade"]
        base = default_runtime_config().scoring_cascade
        return (f"Spend less LLM budget: {_pct(cascade['high_score_llm_fraction'])} of the high-confidence "
                f"bucket goes to the model (default {_pct(base.high_score_llm_fraction)}), and "
                f"{_pct(cascade['low_score_sample_fraction'])} of low-score links are kept for exploration "
                f"(default {_pct(base.low_score_sample_fraction)}).")
    raise KeyError(name)


PRESET_DESCRIPTIONS: dict[str, str] = {name: _preset_description(name, values)
                                       for name, values in BUILTIN_PRESETS.items()}

# The goal guide's three starting points. Each is a patch of settings, and its
# prose is generated from the same values, as the presets' prose is.
GOALS: dict[str, dict] = {
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
            "scoring_cascade": {"low_score_sample_fraction": 0.2, "default_priority_strategy": "exploration"},
            "priority": {"nlp_bias": 85, "llm_bias": 15},
        },
    },
}


def _goal_description(name: str, values: dict) -> str:
    if name == "gentler":
        return f"Waits longer between requests and fetches fewer pages at once: {_pace(values)}."
    if name == "cheaper":
        return _preset_description("frugal", values)
    if name == "explore":
        cascade = values["scoring_cascade"]
        priority = values["priority"]
        return (f"Keeps {_pct(cascade['low_score_sample_fraction'])} of doubtful links for the LLM, orders the "
                f"queue with the {cascade['default_priority_strategy']} strategy, and weighs the NLP score "
                f"{_num(priority['nlp_bias'])} to the LLM's {_num(priority['llm_bias'])}.")
    raise KeyError(name)


def goals() -> dict[str, dict]:
    return {name: {"label": g["label"], "values": g["values"],
                   "description": _goal_description(name, g["values"])}
            for name, g in GOALS.items()}
_PRESET_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,39}$")


def _presets_file():
    return _paths().settings_file.with_name("presets.json")


def _read_presets() -> dict:
    try:
        data = json.loads(_presets_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _check_preset_name(name: str) -> None:
    if name in BUILTIN_PRESETS or not _PRESET_NAME.match(name):
        raise HTTPException(status_code=422, detail=f"Invalid preset name '{name}'")


@router.get("/config/export")
def export_config() -> dict:
    return store.read_stored(_paths().settings_file)


@router.get("/config/presets")
def list_presets() -> dict:
    return {"builtin": BUILTIN_PRESETS, "labels": PRESET_LABELS, "descriptions": PRESET_DESCRIPTIONS,
            "user": _read_presets(), "goals": goals()}


@router.put("/config/presets/{name}")
def save_preset(name: str, body: ConfigPatch | None = None) -> dict:
    _check_preset_name(name)
    values = body.values if body and body.values else store.read_stored(_paths().settings_file)
    try:
        store.load_runtime_config(None, values)
    except ValidationError as exc:
        raise _422(exc)
    presets = _read_presets()
    presets[name] = values
    store._write(_presets_file(), presets)
    return {"saved": name}


@router.delete("/config/presets/{name}")
def delete_preset(name: str) -> dict:
    presets = _read_presets()
    if presets.pop(name, None) is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    store._write(_presets_file(), presets)
    return {"removed": name}


@router.post("/config/presets/{name}/apply")
def apply_preset(name: str) -> dict:
    values = BUILTIN_PRESETS.get(name) or _read_presets().get(name)
    if values is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    try:
        return store.replace_settings(_paths().settings_file, values).model_dump()
    except ValidationError as exc:
        raise _422(exc)


_SAMPLE_LINKS = [
    ("https://example.org/produce/bananas/ripening-guide", "How bananas ripen",
     "Ethylene gas triggers ripening; a guide for grocers and home cooks."),
    ("https://example.org/about/contact", "Contact us",
     "Write to the editorial team or find our office address."),
    ("https://example.org/produce/fruit-exports", "Fruit exports by country",
     "Tables of banana, mango and pineapple exports since 2010."),
]

# What a person may change in each block, and why the rest is fixed.
_BLOCK_INFO = {
    "system": ("System prompt", "editable", "Who the model is and what it must return."),
    "task": ("Task", "generated", "Fixed wording; the parser expects scores from 0 to 100."),
    "context": ("Context", "generated",
                "Built from the crawl target, the scoring strategy and its wording (edit that wording per strategy)."),
    "candidates": ("Candidates", "generated", "The links of one batch, filled in at crawl time."),
    "rules": ("Rules", "editable", "Scoring rules the model should follow."),
    "output": ("Output format", "locked", "The response parser reads exactly this JSON shape."),
    "constraints": ("Constraints", "locked", "Keeps the answer machine-readable."),
}


class PromptPreviewBody(BaseModel):
    target: str = "bananas"
    strategy: str = "TOPICAL"
    scoring_system: str | None = None
    scoring_rules: str | None = None
    strategy_contexts: dict[str, str] | None = None


@router.post("/config/prompts/preview")
def preview_prompt(body: PromptPreviewBody) -> dict:
    """Render the scoring prompt with sample links, using draft wording
    (nothing is saved). Built by the same `PromptBuilder` a crawl uses."""
    if body.strategy not in STRATEGIES:
        raise HTTPException(status_code=422, detail=f"Unknown scoring strategy '{body.strategy}'")
    builder = PromptBuilder(
        body.target, body.strategy,
        system_prompt=body.scoring_system, rules=body.scoring_rules,
        strategy_contexts=body.strategy_contexts,
    )
    links = [Link(url, anchor, ctx) for url, anchor, ctx in _SAMPLE_LINKS]
    blocks = [
        {"id": name, "title": _BLOCK_INFO[name][0], "kind": _BLOCK_INFO[name][1],
         "note": _BLOCK_INFO[name][2], "text": text}
        for name, text in builder.build_blocks(links)
    ]
    return {"blocks": blocks, "prompt": "\n\n".join(b["text"] for b in blocks)}


@router.get("/config/providers")
def get_providers() -> dict:
    """Registered LLM providers, with the models blueprints already use
    (read from templates/*.json) so the UI can offer them as choices."""
    providers = {name: {"models": [], "keys": 0} for name in LlmHandler.translators}
    templates_dir = _paths().templates_dir
    try:
        names = sorted(os.listdir(templates_dir))
    except OSError:
        names = []
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(templates_dir, name), encoding="utf-8") as f:
                bp = json.load(f)
            pairs = [
                (bp["scoring"]["params"]["scoring_type"],
                 bp["scoring"]["params"]["model_information"]),
                (bp["expansion"]["llm_type"], bp["expansion"]["llm_model"]),
            ]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        for provider, model in pairs:
            if provider in providers and model not in providers[provider]["models"]:
                providers[provider]["models"].append(model)
    for provider, keys in _keys().snapshot().items():
        if provider in providers:
            providers[provider]["keys"] = len(keys)
    return providers


# ---------------------------------------------------------------- keys

def _keys() -> KeyManager:
    path = _paths().keys_file
    if not path.exists():
        path.write_text("{}", encoding="utf-8")
        os.chmod(path, 0o600)
    return KeyManager(keys_file=path)


def _reload_running_keys() -> None:
    """Make a key change visible to the crawl in progress."""
    from routes import run as run_routes

    crawler = run_routes._current_crawler
    manager = getattr(crawler, "key_manager", None)
    if manager is not None:
        manager.reload()


class KeyBody(BaseModel):
    provider: str
    key: str


@router.get("/keys")
def list_keys() -> dict:
    return _keys().snapshot()


@router.post("/keys")
def add_key(body: KeyBody) -> dict:
    if body.provider not in LlmHandler.translators:
        raise HTTPException(status_code=422, detail=f"Unknown provider '{body.provider}'")
    try:
        key_id = _keys().add_key(body.provider, body.key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    _reload_running_keys()
    return {"id": key_id}


@router.delete("/keys/{provider}/{key_id}")
def delete_key(provider: str, key_id: str) -> dict:
    if not _keys().remove_key(provider, key_id):
        raise HTTPException(status_code=404, detail="Key not found")
    _reload_running_keys()
    return {"removed": key_id}
