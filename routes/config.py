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
                        (/config/replace too: an uploaded settings.json copy may carry
                        schema_version and the old pipeline section names)
POST /config/effective  saved settings with per-run overrides applied
GET  /config/export     the stored settings, for download
GET  /config/presets    built-in and saved presets
PUT  /config/presets/{name}          save a preset (body: values, or empty for the current settings)
POST /config/presets/{name}/preview  what applying a preset would change (nothing is saved)
POST /config/presets/{name}/apply    merge a preset over the current settings; replies with the config and `changes`
DELETE /config/presets/{name}
PATCH /config/live      change ui_apply=live fields of the running crawl
POST /config/reset      drop one section (?section=) or everything
POST /config/prompts/preview  the scoring prompt as the LLM receives it, from draft wording
GET  /config/providers  LLM providers and the models templates use
GET/POST/DELETE /keys   masked key management (full keys never returned)

Access: every route of the API, these included, requires ``Authorization: Bearer
<token>``; the session token middleware (routes/session_token.py) enforces it.

Changes apply from the next crawl: pipelines copy their values at
construction. Fields flagged ``ui_apply: live`` can also be pushed to the
running crawl with PATCH /config/live (not persisted; PUT /config does that).
"""

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from config import settings_store as store
from config.runtime_config import RuntimeConfig, default_runtime_config
from core.live_settings import LiveSettingsError
from crawlviz.llm.llm_handler import LlmHandler
from crawlviz.shared import Link, load_json
from models.prompts import STRATEGIES, PromptBuilder

from . import run as run_routes
from .config_presets import router as presets_router
from .config_support import (
    ConfigPatch,
    get_paths,
    report_settings_file_errors,
    validation_http_error,
)
from .keys import get_key_manager
from .keys import router as keys_router

router = APIRouter(tags=["config"], dependencies=[Depends(report_settings_file_errors)])
router.include_router(presets_router)
router.include_router(keys_router)


SAVED_SETTINGS_INVALID_MESSAGE = (
    "The saved settings are not valid. Fix the listed settings, or reset them from the config page."
)


@router.get("/config/schema")
def get_config_schema() -> dict:
    """JSON Schema for RuntimeConfig, including the ui_* hints used by the
    frontend's generic schema-driven form renderer."""
    return RuntimeConfig.model_json_schema()


@router.get("/config")
def get_config() -> dict:
    """The runtime configuration currently in effect."""
    try:
        return store.load_runtime_config(get_paths().settings_file).model_dump()
    except ValidationError as exc:
        raise validation_http_error(exc, SAVED_SETTINGS_INVALID_MESSAGE)
    except store.SettingsFileError as exc:
        # Settings that parse but hold invalid values list each entry, so the form can show them.
        if isinstance(exc.__cause__, ValidationError):
            raise validation_http_error(exc.__cause__, str(exc)) from exc
        raise


@router.get("/config/defaults")
def get_defaults() -> dict:
    return default_runtime_config().model_dump()


@router.get("/config/stored")
def get_stored() -> dict:
    return store.read_stored(get_paths().settings_file)


@router.put("/config")
def put_config(body: ConfigPatch) -> dict:
    try:
        return store.save_settings(get_paths().settings_file, body.values).model_dump()
    except ValidationError as exc:
        raise validation_http_error(exc)


@router.put("/config/replace")
def replace_config(body: ConfigPatch) -> dict:
    try:
        uploaded = store.load_uploaded_settings(body.values)
        return store.replace_settings(get_paths().settings_file, uploaded).model_dump()
    except ValidationError as exc:
        raise validation_http_error(exc)


@router.post("/config/validate")
def validate_config(body: ConfigPatch) -> dict:
    try:
        uploaded = store.load_uploaded_settings(body.values)
        store.load_runtime_config(get_paths().settings_file, uploaded)
    except ValidationError as exc:
        return {"valid": False, "errors": store.validation_errors(exc)}
    return {"valid": True, "errors": []}


@router.post("/config/effective")
def effective_config(body: ConfigPatch) -> dict:
    try:
        return store.load_runtime_config(get_paths().settings_file, body.values).model_dump()
    except ValidationError as exc:
        raise validation_http_error(exc)


@router.patch("/config/live")
def patch_live(body: ConfigPatch) -> dict:
    crawler = run_routes._current_crawler
    if crawler is None:
        raise HTTPException(status_code=409, detail="No active crawl")
    try:
        return crawler.apply_live(body.values).model_dump()
    except ValidationError as exc:
        raise validation_http_error(exc)
    except LiveSettingsError as exc:
        raise HTTPException(status_code=422, detail={"errors": [{"path": "", "message": str(exc)}]})


@router.post("/config/reset")
def reset_config(section: str | None = None) -> dict:
    if section is not None and section not in RuntimeConfig.model_fields:
        raise HTTPException(status_code=404, detail=f"Unknown section '{section}'")
    return store.reset_settings(get_paths().settings_file, section).model_dump()


_SAMPLE_LINKS = [
    (
        "https://example.org/produce/bananas/ripening-guide",
        "How bananas ripen",
        "Ethylene gas triggers ripening; a guide for grocers and home cooks.",
    ),
    (
        "https://example.org/about/contact",
        "Contact us",
        "Write to the editorial team or find our office address.",
    ),
    (
        "https://example.org/produce/fruit-exports",
        "Fruit exports by country",
        "Tables of banana, mango and pineapple exports since 2010.",
    ),
]

# What a person may change in each block, and why the rest is fixed.
_BLOCK_INFO = {
    "system": ("System prompt", "editable", "Who the model is and what it must return."),
    "task": ("Task", "generated", "Fixed wording; the parser expects scores from 0 to 100."),
    "context": (
        "Context",
        "generated",
        "Built from the crawl target, the scoring strategy and its wording (edit that wording per strategy).",
    ),
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
        body.target,
        body.strategy,
        system_prompt=body.scoring_system,
        rules=body.scoring_rules,
        strategy_contexts=body.strategy_contexts,
    )
    links = [Link(url, anchor, ctx) for url, anchor, ctx in _SAMPLE_LINKS]
    blocks = [
        {
            "id": name,
            "title": _BLOCK_INFO[name][0],
            "kind": _BLOCK_INFO[name][1],
            "note": _BLOCK_INFO[name][2],
            "text": text,
        }
        for name, text in builder.build_blocks(links)
    ]
    return {"blocks": blocks, "prompt": "\n\n".join(b["text"] for b in blocks)}


@router.get("/config/providers")
def get_providers() -> dict:
    """Registered LLM providers, with the models blueprints already use
    (read from templates/*.json) so the UI can offer them as choices."""
    providers = {name: {"models": [], "keys": 0} for name in LlmHandler.translators}
    templates_dir = get_paths().templates_dir
    try:
        names = sorted(os.listdir(templates_dir))
    except OSError:
        names = []
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            bp = load_json(os.path.join(templates_dir, name))
            pairs = [
                (
                    bp["scoring"]["params"]["scoring_type"],
                    bp["scoring"]["params"]["model_information"],
                ),
                (bp["expansion"]["llm_type"], bp["expansion"]["llm_model"]),
            ]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        for provider, model in pairs:
            if provider in providers and model not in providers[provider]["models"]:
                providers[provider]["models"].append(model)
    for provider, keys in get_key_manager().snapshot().items():
        if provider in providers:
            providers[provider]["keys"] = len(keys)
    return providers


@router.get("/config/export")
def export_config() -> dict:
    return store.read_stored(get_paths().settings_file)
