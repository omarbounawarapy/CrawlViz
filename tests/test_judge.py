"""The 0/1/2 judge retries with a changed prompt until every page has a valid label."""
import asyncio
from typing import Any

import pytest

from benchmark import judge as judge_module
from models.llm_context import LlmContext

ROWS = [
    {"id": "a", "title": "Alpha", "excerpt": "first page"},
    {"id": "b", "title": "Beta", "excerpt": "second page"},
]


class ScriptedLlm:
    """Answers with the scripted replies in order, repeating the last one."""

    def __init__(self, answers: list[dict[str, Any]]) -> None:
        self.answers = answers
        self.prompts: list[str] = []

    async def send(self, context: LlmContext) -> dict[str, Any]:
        self.prompts.append(context.prompt)
        return self.answers[min(len(self.prompts), len(self.answers)) - 1]


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", instant)


def test_valid_answer_maps_page_numbers_to_row_ids() -> None:
    llm = ScriptedLlm([{"labels": {"1": 2, "2": 0}}])
    assert asyncio.run(judge_module.judge(llm, ROWS)) == {"a": 2, "b": 0}


def test_incomplete_answer_is_retried_with_a_changed_prompt() -> None:
    llm = ScriptedLlm(
        [{"labels": {"1": 1}}, {"labels": {"1": 1, "2": "x"}}, {"labels": {"1": 1, "2": 0}}]
    )
    assert asyncio.run(judge_module.judge(llm, ROWS)) == {"a": 1, "b": 0}
    assert len(set(llm.prompts)) == 3


def test_no_usable_answer_raises_after_the_attempt_limit() -> None:
    llm = ScriptedLlm([{}])
    with pytest.raises(RuntimeError, match="no usable answer"):
        asyncio.run(judge_module.judge(llm, ROWS))
    assert len(llm.prompts) == judge_module.MAX_ATTEMPTS
