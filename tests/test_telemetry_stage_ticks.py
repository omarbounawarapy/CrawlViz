"""Filtering and priority close their PIPELINE_EVENT ticks, so the stage panel
shows how long each took."""

from types import SimpleNamespace

from ui_bridge import CrawlStateSnapshot, TelemetryBridge

NODE_ID = 7


class _Gateway:
    async def broadcast(self, message: dict) -> None:
        pass


def _bridge() -> TelemetryBridge:
    return TelemetryBridge(CrawlStateSnapshot(), _Gateway())


def _node() -> SimpleNamespace:
    return SimpleNamespace(get_id=lambda: NODE_ID)


def _ticks(messages: list[dict], stage: str) -> list[dict]:
    return [m for m in messages if m["type"] == "PIPELINE_EVENT" and m["stage"] == stage]


def test_content_filtered_completes_the_filtering_tick_with_a_duration() -> None:
    bridge = _bridge()
    bridge._tick(stage="filtering", phase="started", node_id=str(NODE_ID))
    event = SimpleNamespace(
        node=_node(),
        accepted_links_count=4,
        rejected_links_count=1,
        accepted_items_count=1,
    )

    messages = bridge._on_content_filtered(event)

    assert messages[0]["type"] == "NODE_STATE_CHANGED"
    (tick,) = _ticks(messages, "filtering")
    assert tick["phase"] == "completed" and tick["duration_ms"] is not None
    assert bridge.snapshot.pipeline_stats["filtering"].completed == 1


def test_priority_calculated_completes_the_priority_tick_with_a_duration() -> None:
    bridge = _bridge()
    bridge._tick(stage="priority", phase="started", node_id=str(NODE_ID))
    link = SimpleNamespace(url="https://example.test/a")
    event = SimpleNamespace(parent=_node(), links=[{"link": link, "score": 5, "priority": 0.5}])

    messages = bridge._on_priority_calculated(event)

    assert messages[0]["type"] == "NODE_EXPANDED"
    (tick,) = _ticks(messages, "priority")
    assert tick["phase"] == "completed" and tick["duration_ms"] is not None
    assert bridge.snapshot.pipeline_stats["priority"].completed == 1
