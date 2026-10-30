"""A link the LLM scored 0 keeps that score in the detail shown for the node."""

from types import SimpleNamespace
from typing import Any

import pytest

from ui_bridge import CrawlStateSnapshot, TelemetryBridge

PARENT_ID = 3
LINK_URL = "https://example.test/a"


class _Gateway:
    async def broadcast(self, message: dict[str, Any]) -> None:  # a wire message (JSON)
        pass


def _detail_for(score: float | None) -> dict[str, Any]:
    # The priority stage reports 0 in its own "score" field for a link no LLM call scored,
    # so the detail has to come from the link's own score.
    bridge = TelemetryBridge(CrawlStateSnapshot(), _Gateway())
    link = SimpleNamespace(url=LINK_URL, score=score)
    parent = SimpleNamespace(get_id=lambda: PARENT_ID)
    event = SimpleNamespace(
        parent=parent, links=[{"link": link, "score": score or 0, "priority": 0.5}]
    )
    bridge._on_priority_calculated(event)
    return bridge._pending_detail[LINK_URL]


@pytest.mark.parametrize("score", [0, 0.0, 7])
def test_a_score_of_zero_is_kept(score: float) -> None:
    assert _detail_for(score)["llm_score"] == score


def test_a_link_the_llm_did_not_score_has_no_llm_score() -> None:
    assert _detail_for(None)["llm_score"] is None
