"""The status board of one crawl: what each subsystem reports, in one place (ADR 8).

``StatusBoard`` satisfies ``crawlviz.events.StatusReporter`` by shape, so a producer is
given the board without importing this package. A report is validated and applied under a
lock, in time independent of the size of the crawl. Listeners hear about a report only when
it changes the board, so a producer that repeats itself costs one lock and one comparison.

Producers may run on worker threads (the embedder loads in one), so the board is safe to
report to from any thread. Listeners run on the reporting thread, outside the lock, and must
return quickly; ``StatusObserver`` hands the change to the event loop.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from crawlviz.contracts import (
    StatusBoardSnapshot,
    SubsystemFacts,
    SubsystemName,
    SubsystemState,
    SubsystemStatus,
    apply_report,
    initial_board,
    make_report,
)

logger = logging.getLogger(__name__)

StatusListener = Callable[[SubsystemStatus], None]


class StatusBoard:
    """Holds the current ``StatusBoardSnapshot`` and tells listeners what changed."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._board = initial_board(clock())
        self._listeners: tuple[StatusListener, ...] = ()

    def snapshot(self) -> StatusBoardSnapshot:
        """The board now. It never changes after it is returned."""
        with self._lock:
            return self._board

    def add_listener(self, listener: StatusListener) -> None:
        """Call ``listener`` with the new entry each time a report changes the board."""
        with self._lock:
            self._listeners = (*self._listeners, listener)

    def remove_listener(self, listener: StatusListener) -> None:
        with self._lock:
            self._listeners = tuple(other for other in self._listeners if other != listener)

    def report(
        self,
        subsystem: SubsystemName,
        state: SubsystemState,
        reason: str | None = None,
        facts: SubsystemFacts | None = None,
        *,
        retry_at: float | None = None,
    ) -> None:
        """Record ``subsystem``'s state.

        Raises ``pydantic.ValidationError`` when the reason is not in the subsystem's list,
        the facts belong to another subsystem or a state that needs a reason has none: that
        is a bug in the producer, and the board is left as it was.
        """
        entry = make_report(subsystem, state, reason, facts, self._clock(), retry_at)
        with self._lock:
            updated = apply_report(self._board, entry)
            if updated is self._board:
                return
            self._board = updated
            listeners = self._listeners
        changed = updated.subsystems[subsystem]
        for listener in listeners:
            self._notify(listener, changed)

    @staticmethod
    def _notify(listener: StatusListener, entry: SubsystemStatus) -> None:
        # A listener that fails must not stop the subsystem that reported: the report is
        # already on the board. The failure is logged with its context, not dropped.
        try:
            listener(entry)
        except Exception:
            logger.exception("A status listener failed for the %s subsystem", entry.subsystem)
