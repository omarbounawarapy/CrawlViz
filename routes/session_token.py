"""The token every API route requires, and how the UI gets it.

The token is ``CRAWLVIZ_API_TOKEN`` when that is set (a deployment that gives the UI the
same value as ``VITE_API_TOKEN``). Otherwise one is generated when the API starts and lives
only in memory, so each API process has its own and nothing is written to disk or to a log.

The UI reads a generated token from ``GET /session``. That route is safe to leave without a
token because the request guards (``routes/request_guards.py``) run first: a rebound
hostname fails the Host check and a page on another site fails the Origin check, and the
browser withholds the reply from any origin CORS does not allow. A script on the same
machine can read it, as it could read the files the API itself can.
"""

import hmac
import os
import secrets

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

TOKEN_ENV_VAR = "CRAWLVIZ_API_TOKEN"
GENERATED_TOKEN_BYTES = 32
BEARER_PREFIX = "Bearer "

# Routes that answer without the token: the bootstrap that hands it out, and the
# interactive API documentation FastAPI serves (a browser cannot add a header to those).
TOKEN_EXEMPT_PATHS = frozenset(
    {"/session", "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
)
STATUS_UNAUTHORIZED = 401

_generated_token = secrets.token_urlsafe(GENERATED_TOKEN_BYTES)

router = APIRouter(tags=["session"])


class SessionReply(BaseModel):
    token: str


def get_session_token() -> str:
    """The token in force: the environment's when set, else the one made at startup."""
    return os.environ.get(TOKEN_ENV_VAR) or _generated_token


def authorization_matches(authorization: str | None) -> bool:
    """Whether an ``Authorization: Bearer <token>`` header carries the session token."""
    if authorization is None or not authorization.startswith(BEARER_PREFIX):
        return False
    supplied = authorization.removeprefix(BEARER_PREFIX).strip()
    return hmac.compare_digest(supplied.encode(), get_session_token().encode())


@router.get("/session", response_model=SessionReply)
def get_session() -> SessionReply:
    """The generated token, for the UI to send as ``Authorization: Bearer``."""
    if os.environ.get(TOKEN_ENV_VAR):
        raise HTTPException(
            status_code=404,
            detail=(
                f"The API token comes from {TOKEN_ENV_VAR}, so it is not served here. "
                "Build the UI with the same value as VITE_API_TOKEN."
            ),
        )
    return SessionReply(token=_generated_token)


class SessionTokenMiddleware:
    """ASGI middleware: every HTTP request but the exempt paths needs the session token."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # A CORS preflight carries no credentials by design and is answered by the CORS
        # middleware outside this one; the WebSocket gateway checks its own origins.
        exempt = (
            scope["type"] != "http"
            or scope["method"] == "OPTIONS"
            or scope["path"] in TOKEN_EXEMPT_PATHS
        )
        if exempt or authorization_matches(Headers(scope=scope).get("authorization")):
            await self._app(scope, receive, send)
            return
        response = JSONResponse(
            {
                "detail": (
                    "The API token is missing or wrong. Reload the app so it fetches a "
                    "current one, or set VITE_API_TOKEN to the value of CRAWLVIZ_API_TOKEN."
                )
            },
            status_code=STATUS_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )
        await response(scope, receive, send)
