"""The stop controller ends a crawl whose frontier has run dry, and only then."""

import asyncio
from collections.abc import Callable

from crawlviz.events import StopCrawlEvent
from pipelines.stop_controller import IDLE_CONFIRMATION_CHECKS, StopConditions, StopController

CHECK_INTERVAL = 0.01
WAIT_CHECKS = IDLE_CONFIRMATION_CHECKS * 4
LONG_TIME = 3600.0


class RecordingBroker:
    def __init__(self) -> None:
        self.events: list[StopCrawlEvent] = []

    async def emit(self, event: StopCrawlEvent) -> None:
        self.events.append(event)


async def _run_controller(frontier_idle: Callable[[], bool] | None) -> list[StopCrawlEvent]:
    broker = RecordingBroker()
    controller = StopController(
        broker,
        StopConditions(
            max_nodes=10,
            max_duration=LONG_TIME,
            no_progress_timeout=LONG_TIME,
            frontier_idle=frontier_idle,
        ),
        check_interval=CHECK_INTERVAL,
    )
    task = asyncio.create_task(controller.start())
    await asyncio.sleep(CHECK_INTERVAL * WAIT_CHECKS)
    await controller.stop()
    await asyncio.wait_for(task, 5)
    return broker.events


async def test_an_idle_frontier_stops_the_crawl_with_its_own_reason() -> None:
    events = await _run_controller(lambda: True)

    assert [event.reason for event in events] == ["FRONTIER_EXHAUSTED"]


async def test_work_that_keeps_coming_back_does_not_stop_the_crawl() -> None:
    checks = iter(range(10**6))

    def idle_but_never_for_long() -> bool:
        return next(checks) % IDLE_CONFIRMATION_CHECKS != 0

    assert await _run_controller(idle_but_never_for_long) == []


async def test_a_busy_frontier_does_not_stop_the_crawl() -> None:
    assert await _run_controller(lambda: False) == []


async def test_a_controller_without_a_probe_never_reports_a_drained_frontier() -> None:
    assert await _run_controller(None) == []
