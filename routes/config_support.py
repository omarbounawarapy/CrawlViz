"""Pieces the config, preset and key routers share."""

import hmac
import os
from typing import Any

from fastapi import Header, HTTPException
from pydantic import BaseModel, ValidationError

from config import RuntimePaths, default_runtime_paths


def require_token(authorization: str | None = Header(default=None)) -> None:
    token = os.environ.get("CRAWLVIZ_API_TOKEN")
    if not token:
        return
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(status_code=401, detail="Missing or invalid API token")


def get_paths() -> RuntimePaths:
    return default_runtime_paths()


def validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [{"path": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]


def validation_http_error(exc: ValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail={"errors": validation_errors(exc)})


class ConfigPatch(BaseModel):
    values: dict[str, Any]
