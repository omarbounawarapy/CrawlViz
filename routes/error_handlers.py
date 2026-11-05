"""App-level error replies that must not repeat what the client sent."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

STATUS_UNPROCESSABLE = 422
# FastAPI's default reply also holds ``input`` (the submitted value) and ``ctx`` (the
# validator's context). Either can carry a secret, such as an API key sent to POST /keys.
KEPT_PROBLEM_FIELDS = ("type", "loc", "msg")


def drop_submitted_values(
    problems: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep where each problem is, what it is and why, and nothing the client sent."""
    return [
        {field: problem[field] for field in KEPT_PROBLEM_FIELDS if field in problem}
        for problem in problems
    ]


async def reply_to_invalid_request(_request: Request, exc: Exception) -> JSONResponse:
    """The 422 for a request that fails validation, in FastAPI's shape without the values."""
    if not isinstance(exc, RequestValidationError):
        raise exc
    detail = drop_submitted_values(list(exc.errors()))
    return JSONResponse(
        status_code=STATUS_UNPROCESSABLE, content={"detail": jsonable_encoder(detail)}
    )


def register_error_handlers(app: FastAPI) -> None:
    """Install the handlers on ``app``; they apply to every route."""
    app.add_exception_handler(RequestValidationError, reply_to_invalid_request)
