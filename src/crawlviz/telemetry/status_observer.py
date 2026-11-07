"""Passes the status board's changes on, at most once per window for each subsystem (ADR 8).

A subsystem such as the LLM client reports every call, which is far more often than a screen
needs. ``StatusObserver`` sends the first change of a subsystem at once, then holds later
changes for that subsystem until ``STATUS_COALESCE_MS`` has passed since the last send and
sends only the newest entry. Subsystems do not hold each other back, and an entry that is
back to what was last sent is not sent again.

The board calls its listeners on whatever thread reported. The observer moves each change
onto the event loop it was started on and sends from there, so ``send`` runs on the loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from crawlviz.contracts import SubsystemName, SubsystemStatus

from .status_board import StatusBoard

logger = logging.getLogger(__name__)

# The shortest time between two sends for one subsystem. The UI redraws no faster than this.
STATUS_COALESCE_MS = 250

StatusSender = Callable[[SubsystemStatus], Awaitable[None]]


class StatusObserver:
    """Sends the entries of a ``StatusBoard`` that changed, coalesced per subsystem."""

    def __init__(
        self,
        board: StatusBoard,
        send: StatusSender,
        coalesce_ms: float = STATUS_COALESCE_MS,
    ) -> None:
        self._board = board
        self._send = send
        self._window_seconds = coalesce_ms / 1000
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_sent_at: dict[SubsystemName, float] = {}
        self._last_sent: dict[SubsystemName, SubsystemStatus] = {}
        self._flushes: dict[SubsystemName, asyncio.TimerHandle] = {}
        self._sending: set[asyncio.Task[None]] = set()

    def start(self) -> None:
        """Begin watching the board. Call it on the event loop the sends should run on."""
        self._loop = asyncio.get_running_loop()
        self._board.add_listener(self._on_board_change)

    async def stop(self) -> None:
        """Stop watching, send what is being held so the last state is not lost, and wait."""
        self._board.remove_listener(self._on_board_change)
        for name in list(self._flushes):
            self._flushes.pop(name).cancel()
            self._flush(name)
        if self._sending:
            await asyncio.gather(*self._sending)

    def _on_board_change(self, entry: SubsystemStatus) -> None:
        """Runs on the reporting thread: hand the change to the loop and return."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        with contextlib.suppress(RuntimeError):  # the loop closed between the check and here
            loop.call_soon_threadsafe(self._schedule, entry.subsystem)

    def _schedule(self, name: SubsystemName) -> None:
        if name in self._flushes:
            return  # a send is already due; it reads the newest entry when it runs
        loop = asyncio.get_running_loop()
        wait = self._last_sent_at.get(name, float("-inf")) + self._window_seconds - loop.time()
        if wait <= 0:
            self._flush(name)
        else:
            self._flushes[name] = loop.call_later(wait, self._flush, name)

    def _flush(self, name: SubsystemName) -> None:
        self._flushes.pop(name, None)
        entry = self._board.snapshot().subsystems[name]
        if entry == self._last_sent.get(name):
            return
        self._last_sent[name] = entry
        self._last_sent_at[name] = asyncio.get_running_loop().time()
        task = asyncio.get_running_loop().create_task(self._deliver(entry))
        self._sending.add(task)
        task.add_done_callback(self._sending.discard)

    async def _deliver(self, entry: SubsystemStatus) -> None:
        try:
            await self._send(entry)
        except Exception:
            # One failed send must not end the stream: the next change is sent again.
            logger.exception("Sending the %s status failed", entry.subsystem)
