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

TOKEN_ENV_VAR = "CRAWLVIZ_API_TOKEN"
GENERATED_TOKEN_BYTES = 32
BEARER_PREFIX = "Bearer "

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
