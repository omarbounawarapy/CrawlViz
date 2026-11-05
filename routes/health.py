"""Liveness: is the process up.

``GET /health`` answers while the process runs and touches nothing, so a probe that fails
here means the process is down or stuck.

It sits behind the session token and the Host and Origin checks like every other route:
it leaks nothing, but nothing needs it open either, because the UI and local tools hold
the token (docs/adr/0008-subsystem-status.md).
"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthReply(BaseModel):
    status: Literal["ok"]


@router.get("/health", response_model=HealthReply)
def get_health() -> HealthReply:
    """The process is up. Nothing is read or written."""
    return HealthReply(status="ok")
