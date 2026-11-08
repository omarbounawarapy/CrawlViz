"""Pieces the config, preset and key routers share."""

from collections.abc import Iterator
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from config import RuntimePaths, default_runtime_paths
from config.settings_store import SettingsFileError


def report_settings_file_errors() -> Iterator[None]:
    """Answer a damaged settings file with its plain-words message instead of a raw 500."""
    try:
        yield
    except SettingsFileError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def get_paths() -> RuntimePaths:
    return default_runtime_paths()


def validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [{"path": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]


def validation_http_error(exc: ValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail={"errors": validation_errors(exc)})


class ConfigPatch(BaseModel):
    values: dict[str, Any]
