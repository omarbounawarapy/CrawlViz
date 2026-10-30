"""A link the LLM scored 0 keeps that score in the detail shown for the node."""

from types import SimpleNamespace

import pytest

from ui_bridge import CrawlStateSnapshot, TelemetryBridge

PARENT_ID = 3
LINK_URL = "https://example.test/a"


class _Gateway:
    async def broadcast(self, message: dict) -> None:
        pass


def _detail_for(score) -> dict:
    bridge = TelemetryBridge(CrawlStateSnapshot(), _Gateway())
    link = SimpleNamespace(url=LINK_URL)
    parent = SimpleNamespace(get_id=lambda: PARENT_ID)
    event = SimpleNamespace(parent=parent, links=[{"link": link, "score": score, "priority": 0.5}])
    bridge._on_priority_calculated(event)
    return bridge._pending_detail[LINK_URL]


@pytest.mark.parametrize("score", [0, 0.0, 7])
def test_a_score_of_zero_is_kept(score) -> None:
    assert _detail_for(score)["llm_score"] == score


def test_a_link_the_llm_did_not_score_has_no_llm_score() -> None:
    assert _detail_for(None)["llm_score"] is None
