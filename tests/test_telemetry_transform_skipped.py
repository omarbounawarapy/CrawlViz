"""A transform step skipped for an over-long field shows up as a crawl error in the live view."""

from typing import Any

from events import TransformationStepSkippedEvent
from ui_bridge import CrawlStateSnapshot, TelemetryBridge


class FakeNode:
    def get_id(self) -> int:
        return 7


class RecordingGateway:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def broadcast(self, message: dict[str, Any]) -> None:
        self.sent.append(message)


async def test_a_skipped_step_becomes_a_node_error_that_says_what_was_left_unchanged() -> None:
    snapshot = CrawlStateSnapshot()
    gateway = RecordingGateway()
    bridge = TelemetryBridge(snapshot, gateway)
    bridge.register_handlers()

    await bridge.put(
        TransformationStepSkippedEvent(
            correlation_id="7",
            node=FakeNode(),
            transform_type="regex",
            input_length=120_000,
            limit=100_000,
        )
    )

    [message] = gateway.sent
    assert message["type"] == "NODE_ERROR"
    assert message["node_id"] == "7"
    assert message["stage"] == "transformation"
    assert message["error_type"] == "TransformSkipped"
    assert "120000 characters" in message["error_message"]
    assert "limit is 100000" in message["error_message"]
    assert "keeps its value" in message["error_message"]
    assert snapshot.to_full_snapshot()["errors"][-1]["error_type"] == "TransformSkipped"
