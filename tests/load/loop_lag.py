"""Event-loop lag: how late a task that asked to wake every few milliseconds actually wakes.

A coroutine that blocks the loop (CPU work in a handler, a synchronous disk write) delays
every other task by as long as it runs. A background task that sleeps ``interval`` seconds
and records how much later than that it woke sees those stalls, whatever stage caused them.
"""

import asyncio
import math
from dataclasses import dataclass

SAMPLE_INTERVAL_SECONDS = 0.01
MILLISECONDS = 1000.0
MEDIAN_PERCENT = 50.0
TAIL_PERCENT = 99.0
PERCENT = 100.0


@dataclass(frozen=True)
class LagSummary:
    """Lag in milliseconds over all samples; zeros when nothing was sampled."""

    samples: int
    p50_ms: float
    p99_ms: float
    max_ms: float


def percentile(sorted_values: list[float], percent: float) -> float:
    """Nearest-rank percentile of an ascending list: the smallest value with at least
    ``percent`` of the list at or below it. Zero for an empty list."""
    if not sorted_values:
        return 0.0
    rank = math.ceil(percent / PERCENT * len(sorted_values))
    return sorted_values[max(rank, 1) - 1]


def summarize(lags_seconds: list[float]) -> LagSummary:
    ordered = sorted(lags_seconds)
    return LagSummary(
        samples=len(ordered),
        p50_ms=percentile(ordered, MEDIAN_PERCENT) * MILLISECONDS,
        p99_ms=percentile(ordered, TAIL_PERCENT) * MILLISECONDS,
        max_ms=(ordered[-1] if ordered else 0.0) * MILLISECONDS,
    )


class LoopLagMonitor:
    """Use as ``async with LoopLagMonitor() as monitor``; read ``monitor.summary()`` after.

    One float per sample is kept (about 100 a second), which is small next to the crawl.
    """

    def __init__(self, interval: float = SAMPLE_INTERVAL_SECONDS) -> None:
        self.interval = interval
        self._lags: list[float] = []
        self._task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "LoopLagMonitor":
        self._task = asyncio.create_task(self._sample())
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    def summary(self) -> LagSummary:
        return summarize(self._lags)

    async def _sample(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            due = loop.time() + self.interval
            await asyncio.sleep(self.interval)
            self._lags.append(max(loop.time() - due, 0.0))
