"""Masked API key management. Full keys are never returned."""

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from infrastructure.key_manager import KeyManager
from infrastructure.llm_handler import LlmHandler

from . import run as run_routes
from .config_support import get_paths

router = APIRouter(tags=["config"])


def get_key_manager() -> KeyManager:
    path = get_paths().keys_file
    if not path.exists():
        path.write_text("{}", encoding="utf-8")
        os.chmod(path, 0o600)
    return KeyManager(keys_file=path)


def _reload_running_keys() -> None:
    """Make a key change visible to the crawl in progress."""
    crawler = run_routes._current_crawler
    manager = getattr(crawler, "key_manager", None)
    if manager is not None:
        manager.reload()


class KeyBody(BaseModel):
    provider: str
    key: str


@router.get("/keys")
def list_keys() -> dict[str, Any]:
    return get_key_manager().snapshot()


@router.post("/keys")
def add_key(body: KeyBody) -> dict[str, Any]:
    if body.provider not in LlmHandler.translators:
        raise HTTPException(status_code=422, detail=f"Unknown provider '{body.provider}'")
    try:
        key_id = get_key_manager().add_key(body.provider, body.key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _reload_running_keys()
    return {"id": key_id}


@router.delete("/keys/{provider}/{key_id}")
def delete_key(provider: str, key_id: str) -> dict[str, Any]:
    if not get_key_manager().remove_key(provider, key_id):
        raise HTTPException(status_code=404, detail="Key not found")
    _reload_running_keys()
    return {"removed": key_id}
