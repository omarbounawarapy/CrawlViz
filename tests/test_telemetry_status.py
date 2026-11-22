"""The bridge sends SUBSYSTEM_STATUS when an entry on the status board changes (ADR 8)."""

import asyncio
from typing import Any

import pytest

from crawlviz.contracts import LlmFacts, SubsystemStatusMessage
from crawlviz.events import StopCrawlEvent
from crawlviz.telemetry import StatusBoard
from ui_bridge import CrawlStateSnapshot, TelemetryBridge


class _Gateway:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []  # wire messages (JSON)
        self.stopped = False

    async def broadcast(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    async def stop(self) -> None:
        self.stopped = True


@pytest.fixture
def gateway() -> _Gateway:
    return _Gateway()


@pytest.fixture
def board() -> StatusBoard:
    return StatusBoard()


@pytest.fixture
async def bridge(gateway: _Gateway, board: StatusBoard) -> TelemetryBridge:
    bridge = TelemetryBridge(CrawlStateSnapshot(), gateway)
    bridge.register_handlers()
    bridge.watch_status(board)
    return bridge


async def _let_the_loop_run() -> None:
    await asyncio.sleep(0)
    await asyncio.sleep(0)


async def test_a_board_change_is_sent_as_a_subsystem_status_message(
    bridge: TelemetryBridge, board: StatusBoard, gateway: _Gateway
) -> None:
    board.report("embedder", "starting", "loading_model")
    await _let_the_loop_run()

    [message] = gateway.messages
    assert message["type"] == "SUBSYSTEM_STATUS"
    assert message["entry"]["subsystem"] == "embedder"
    assert message["entry"]["reason"] == "loading_model"
    assert SubsystemStatusMessage.model_validate(message).entry.state == "starting"


async def test_a_repeated_report_sends_nothing_more(
    bridge: TelemetryBridge, board: StatusBoard, gateway: _Gateway
) -> None:
    board.report("embedder", "starting", "loading_model")
    await _let_the_loop_run()
    board.report("embedder", "starting", "loading_model")
    await _let_the_loop_run()

    assert len(gateway.messages) == 1


async def test_the_stop_event_sends_the_held_change_then_closes_the_gateway(
    bridge: TelemetryBridge, board: StatusBoard, gateway: _Gateway
) -> None:
    board.report("llm", "ready", None, LlmFacts(calls=1))
    await _let_the_loop_run()
    board.report("llm", "ready", None, LlmFacts(calls=2))
    await _let_the_loop_run()  # held: the 250 ms window has not passed

    await bridge.put(StopCrawlEvent("MANUAL_STOP", 1, 0, 0.0))

    calls = [
        m["entry"]["facts"]["calls"] for m in gateway.messages if m["type"] == "SUBSYSTEM_STATUS"
    ]
    assert calls == [1, 2]
    assert gateway.stopped


async def test_a_bridge_that_watches_no_board_sends_no_status(gateway: _Gateway) -> None:
    bridge = TelemetryBridge(CrawlStateSnapshot(), gateway)
    bridge.register_handlers()

    await bridge.put(StopCrawlEvent("MANUAL_STOP", 1, 0, 0.0))

    assert [m["type"] for m in gateway.messages] == ["CRAWL_STOPPED"]
