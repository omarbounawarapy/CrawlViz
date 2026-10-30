"""Filtering and priority close their PIPELINE_EVENT ticks, so the stage panel
shows how long each took."""

from types import SimpleNamespace

from ui_bridge import CrawlStateSnapshot, TelemetryBridge

NODE_ID = 7
ACCEPTED_LINKS = 4
REJECTED_LINKS = 1
ACCEPTED_ITEMS = 1
LLM_SCORE = 5
ZERO_SCORE = 0
LINK_URL = "https://example.test/a"
PRIORITY = 0.5


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
    link = SimpleNamespace(url=LINK_URL)
    entry = {"link": link, "score": LLM_SCORE, "priority": PRIORITY}
    event = SimpleNamespace(parent=_node(), links=[entry])

    messages = bridge._on_priority_calculated(event)

    assert messages[0]["type"] == "NODE_EXPANDED"
    (tick,) = _ticks(messages, "priority")
    assert tick["phase"] == "completed" and tick["duration_ms"] is not None
    assert bridge.snapshot.pipeline_stats["priority"].completed == 1


def _priority_event_with_link_score(link_score: int | None) -> SimpleNamespace:
    link = SimpleNamespace(url=LINK_URL, score=link_score)
    # The priority stage reports 0 in its own "score" field when there was no LLM score.
    entry = {"link": link, "score": link_score or 0, "priority": PRIORITY}
    return SimpleNamespace(parent=_node(), links=[entry])


def test_an_llm_score_of_zero_reaches_the_node_detail_as_zero() -> None:
    bridge = _bridge()

    bridge._on_priority_calculated(_priority_event_with_link_score(ZERO_SCORE))

    assert bridge._pending_detail[LINK_URL]["llm_score"] == ZERO_SCORE


def test_a_link_the_llm_never_scored_has_no_llm_score_in_the_node_detail() -> None:
    bridge = _bridge()

    bridge._on_priority_calculated(_priority_event_with_link_score(None))

    assert bridge._pending_detail[LINK_URL]["llm_score"] is None
