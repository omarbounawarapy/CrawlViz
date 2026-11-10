"""Pieces the config, preset and key routers share."""

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from config import RuntimePaths, default_runtime_paths


def get_paths() -> RuntimePaths:
    return default_runtime_paths()


def validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    """Field path and message per error. The submitted value and the pydantic docs URL are
    never requested, so a refused key or endpoint cannot travel in the 422 body."""
    errors = exc.errors(include_input=False, include_url=False)
    return [{"path": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in errors]


def validation_http_error(exc: ValidationError, message: str | None = None) -> HTTPException:
    detail: dict[str, Any] = {"errors": validation_errors(exc)}
    if message is not None:
        detail["message"] = message
    return HTTPException(status_code=422, detail=detail)


class ConfigPatch(BaseModel):
    values: dict[str, Any]
