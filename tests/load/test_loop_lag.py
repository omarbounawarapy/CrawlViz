"""The event-loop lag monitor sees a blocked loop and ignores an idle one."""

import asyncio
import time

import pytest

from tests.load.loop_lag import LagSummary, LoopLagMonitor, percentile, summarize

BLOCK_SECONDS = 0.15
WAIT_TIMEOUT_SECONDS = 5.0
MIN_STALL_MS = 100.0
SAMPLE_INTERVAL = 0.005


async def _wait_for_samples(monitor: LoopLagMonitor, count: int) -> None:
    """Yield to the loop until the monitor holds ``count`` samples, or fail after a timeout."""

    async def enough() -> None:
        while monitor.summary().samples < count:
            await asyncio.sleep(SAMPLE_INTERVAL)

    await asyncio.wait_for(enough(), WAIT_TIMEOUT_SECONDS)


def _block_the_loop(seconds: float) -> None:
    """Hold the thread, as CPU work in a handler would, without yielding."""
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        pass


async def test_a_blocked_loop_shows_as_lag() -> None:
    async with LoopLagMonitor(interval=SAMPLE_INTERVAL) as monitor:
        await _wait_for_samples(monitor, 2)
        _block_the_loop(BLOCK_SECONDS)
        await _wait_for_samples(monitor, monitor.summary().samples + 2)

    summary = monitor.summary()
    assert summary.max_ms >= MIN_STALL_MS
    assert summary.p50_ms < summary.max_ms


async def test_the_monitor_leaves_no_task_behind() -> None:
    async with LoopLagMonitor(interval=SAMPLE_INTERVAL) as monitor:
        await _wait_for_samples(monitor, 1)

    assert asyncio.all_tasks() == {asyncio.current_task()}


def test_summary_of_no_samples_is_zero() -> None:
    assert summarize([]) == LagSummary(samples=0, p50_ms=0.0, p99_ms=0.0, max_ms=0.0)


def test_summary_is_in_milliseconds() -> None:
    summary = summarize([0.001, 0.002, 0.003, 0.004])

    assert summary == LagSummary(samples=4, p50_ms=2.0, p99_ms=4.0, max_ms=4.0)


@pytest.mark.parametrize(
    ("percent", "expected"),
    [(50.0, 5), (90.0, 9), (99.0, 10), (100.0, 10), (0.0, 1)],
)
def test_percentile_is_nearest_rank(percent: float, expected: int) -> None:
    assert percentile([float(n) for n in range(1, 11)], percent) == expected


def test_percentile_of_an_empty_list_is_zero() -> None:
    assert percentile([], 99.0) == 0.0
