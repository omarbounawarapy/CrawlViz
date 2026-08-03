"""
Config routes
=============
Exposes RuntimeConfig (config/runtime_config.py) to the frontend's
Configuration section -- "what assumptions is this crawl operating
under?" (docs/V2_ARCHITECTURE.md §B.1).

Read-only in this pass: GET /config/schema returns the JSON Schema
(generated from the Pydantic model, not hand-copied -- see
runtime_config.py's module docstring for why that distinction matters),
GET /config returns the values currently in effect. A write-back path
(PUT /config with validation errors surfaced inline) is scoped as
follow-up work -- see docs/V2_ARCHITECTURE.md roadmap #18 -- rather than
built shallow in the same pass as the protocol overhaul.
"""

from fastapi import APIRouter

from config.runtime_config import RuntimeConfig, default_runtime_config

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/schema")
def get_config_schema() -> dict:
    """JSON Schema for RuntimeConfig, including the ui_section/ui_widget
    hints used by the frontend's generic schema-driven form renderer."""
    return RuntimeConfig.model_json_schema()


@router.get("")
def get_config() -> dict:
    """The runtime configuration currently in effect."""
    return default_runtime_config().model_dump()
