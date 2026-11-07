"""Replies of ``GET /health`` and ``GET /ready``.

These are the shapes ``routes/health.py`` returns today, moved here so the OpenAPI document
and the generated client read them from one place (ADR 5, ADR 12). Until the router imports
them, ``tests/contracts/test_api_schemas.py`` checks the two copies stay the same.
"""

from typing import Literal

from pydantic import BaseModel


class HealthReply(BaseModel):
    """The process is up."""

    status: Literal["ok"]


class ReadinessCheck(BaseModel):
    """One thing ``GET /ready`` verified. ``detail`` says what to fix when ``ok`` is false."""

    name: str
    ok: bool
    detail: str | None = None


class ReadyReply(BaseModel):
    """``ready`` is true when every check passed; the route answers 503 otherwise."""

    ready: bool
    checks: list[ReadinessCheck]
