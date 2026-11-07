"""The crawl's lifecycle state and the ``SUBSYSTEM_STATUS`` wire message (ADR 8).

``CrawlState`` is the one list of lifecycle states. A crawl goes ``idle``, ``starting``,
``running``, ``stopping``, then ends ``stopped`` (by the user), ``finished`` (a limit was
reached) or ``failed``. ``GET /status`` and ``CRAWL_STOPPED`` carry the same value.

``SubsystemStatusMessage`` is what the telemetry observer sends when one subsystem's entry
changes. It carries the whole entry, so the UI replaces that subsystem's entry and never
merges fields. ``docs/crawl_messages.ts`` documents it; ``tests/test_wire_protocol.py``
checks the two agree.
"""

from __future__ import annotations

from typing import Final, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from .subsystem_status import SubsystemStatus

CrawlState = Literal["idle", "starting", "running", "stopping", "stopped", "finished", "failed"]
CrawlEndState = Literal["stopped", "finished", "failed"]

CRAWL_STATES: Final[tuple[CrawlState, ...]] = get_args(CrawlState)
CRAWL_END_STATES: Final[tuple[CrawlEndState, ...]] = get_args(CrawlEndState)

SUBSYSTEM_STATUS: Final = "SUBSYSTEM_STATUS"


class SubsystemStatusMessage(BaseModel):
    """One subsystem's entry changed. ``ts`` is when it was sent (unix seconds)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["SUBSYSTEM_STATUS"] = SUBSYSTEM_STATUS
    ts: float = Field(ge=0)
    entry: SubsystemStatus
