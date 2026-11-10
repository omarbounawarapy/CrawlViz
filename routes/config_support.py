"""Pieces the config, preset and key routers share."""

from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from config import RuntimePaths, default_runtime_paths


def get_paths() -> RuntimePaths:
    return default_runtime_paths()


def validation_errors(exc: ValidationError | RequestValidationError) -> list[dict[str, Any]]:
    """Field path and message per error. The submitted value and the pydantic docs URL are
    never requested, so a refused key or endpoint cannot travel in the 422 body.

    A request error already holds its entries; only the path and message are copied.
    """
    if isinstance(exc, RequestValidationError):
        errors = exc.errors()
    else:
        errors = exc.errors(include_input=False, include_url=False)
    return [{"path": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in errors]


async def request_validation_response(_request: Request, exc: Exception) -> JSONResponse:
    """The 422 for a request that does not fit its route, in the shape the config routes use.

    FastAPI's own answer repeats the submitted body, which can hold a key.
    """
    if not isinstance(exc, RequestValidationError):
        raise exc
    return JSONResponse(status_code=422, content={"detail": {"errors": validation_errors(exc)}})


def validation_http_error(exc: ValidationError, message: str | None = None) -> HTTPException:
    detail: dict[str, Any] = {"errors": validation_errors(exc)}
    if message is not None:
        detail["message"] = message
    return HTTPException(status_code=422, detail=detail)


class ConfigPatch(BaseModel):
    values: dict[str, Any]
