"""How a subsystem tells the crawl what state it is in (ADR 8).

A producer (a stage, the LLM client, the NLP build) is given a ``StatusReporter`` and calls
``report`` when its state or facts change. It never imports ``crawlviz.telemetry``, which
holds the board that records the reports, so the dependency points one way (ADR 4).

``report`` is synchronous and only writes to memory: a producer may call it from a hot path
or from a worker thread, and it must not change scheduling. ``NullStatusReporter`` discards
every report; the benchmark runner and the behaviour pins pass it, so neither records a
board.
"""

from typing import Protocol

from crawlviz.contracts import SubsystemFacts, SubsystemName, SubsystemState


class StatusReporter(Protocol):
    """Receives one subsystem's current state.

    ``reason`` is a code from the subsystem's closed list (``crawlviz.contracts``), never a
    sentence. ``facts`` is that subsystem's facts model, or ``None`` to keep the defaults.
    ``retry_at`` is unix seconds and only for a ``waiting`` state.
    """

    def report(
        self,
        subsystem: SubsystemName,
        state: SubsystemState,
        reason: str | None = None,
        facts: SubsystemFacts | None = None,
        *,
        retry_at: float | None = None,
    ) -> None: ...


class NullStatusReporter:
    """A reporter that discards every report."""

    def report(
        self,
        subsystem: SubsystemName,
        state: SubsystemState,
        reason: str | None = None,
        facts: SubsystemFacts | None = None,
        *,
        retry_at: float | None = None,
    ) -> None:
        return None
