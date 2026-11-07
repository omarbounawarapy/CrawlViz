"""The stop controller ends a crawl whose frontier has run dry, and only then."""

import asyncio
from collections.abc import Callable

import pytest

from core.event_broker import EventBroker
from core.stages import STAGES, _frontier_probe
from crawlviz.events import CrawlStage, StopCrawlEvent
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


class _Tracked:
    def __init__(self, busy: bool) -> None:
        self.has_pending_work = busy


def _built(busy_key: str | None, untracked_key: str | None = None) -> dict[str, CrawlStage]:
    built: dict[str, CrawlStage] = {}
    for spec in STAGES:
        built[spec.key] = object() if spec.key == untracked_key else _Tracked(spec.key == busy_key)  # type: ignore[assignment]  # doubles stand in for stages
    return built


def test_the_probe_is_idle_when_no_stage_that_feeds_the_frontier_holds_work() -> None:
    assert _frontier_probe(EventBroker(), _built(busy_key=None))()


def test_the_probe_sees_work_in_any_stage_that_feeds_the_frontier() -> None:
    feeding = [spec.key for spec in STAGES if spec.feeds_frontier]

    assert feeding
    assert not any(_frontier_probe(EventBroker(), _built(busy_key=key))() for key in feeding)


def test_the_probe_does_not_ask_the_stages_that_are_sinks() -> None:
    sinks = [spec.key for spec in STAGES if not spec.feeds_frontier]

    assert sinks
    assert all(_frontier_probe(EventBroker(), _built(busy_key=key))() for key in sinks)


def test_a_stage_that_feeds_the_frontier_but_cannot_report_work_fails_the_build() -> None:
    with pytest.raises(TypeError, match="has_pending_work"):
        _frontier_probe(EventBroker(), _built(busy_key=None, untracked_key="scoring"))
