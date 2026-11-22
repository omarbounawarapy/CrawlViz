"""Background tasks that are held, reported when they fail, and cancelled on shutdown."""

import asyncio
import logging
from collections.abc import Coroutine, Iterator
from typing import Any

logger = logging.getLogger(__name__)


class BackgroundTasks:
    """Owns the tasks an object starts and does not await itself.

    A bare ``asyncio.create_task`` result that nobody keeps can be garbage
    collected mid-run, and its exception is only noticed at interpreter exit.
    ``spawn`` keeps the task until it ends and logs a failure with the task's name.
    """

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()

    def spawn(self, coro: Coroutine[Any, Any, Any], name: str) -> asyncio.Task[Any]:
        """Start ``coro`` as a task; ``name`` appears in the log if it fails."""
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._finished)
        return task

    def _finished(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error("Background task %s failed", task.get_name(), exc_info=error)

    def __len__(self) -> int:
        return len(self._tasks)

    def __iter__(self) -> Iterator[asyncio.Task[Any]]:
        """The tasks still running, so a caller can ``gather(*tasks)`` to wait for them."""
        return iter(list(self._tasks))

    async def cancel_all(self) -> None:
        """Cancel every task still running and wait for each to end."""
        pending = list(self._tasks)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
