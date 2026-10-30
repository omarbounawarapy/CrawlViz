"""One parser for model replies, pydantic validation, and repair only when turned on."""

import pytest
from pydantic import BaseModel

from crawlviz.score.llm.json_output import (
    MAX_REPLY_CHARS,
    LlmOutputError,
    parse_llm_json,
    validate_llm_output,
)


class Scores(BaseModel):
    results: dict[str, int]


class RepairRecorder:
    """Stands in for the repair LLM call and records what it was asked."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, reply: str, problem: str) -> str:
        self.calls.append((reply, problem))
        return self.answer


@pytest.mark.parametrize(
    "reply",
    [
        '{"results": {"a": 1}}',
        '```json\n{"results": {"a": 1}}\n```',
        '```\n{"results": {"a": 1}}\n```',
        'Here are the scores:\n{"results": {"a": 1}}\nHope this helps.',
        '  {"results": {"a": 1}}  \n',
    ],
)
def test_parse_accepts_the_shapes_models_send(reply: str) -> None:
    assert parse_llm_json(reply) == {"results": {"a": 1}}


@pytest.mark.parametrize(
    ("reply", "problem"),
    [
        ("no json here", "no JSON object"),
        ("[1, 2]", "JSON list, not an object"),
        ('{"results": {"a": 1}', "not valid JSON"),
        ('{"a": 1} and {"b": 2}', "not valid JSON"),
    ],
)
def test_parse_refuses_what_is_not_one_object(reply: str, problem: str) -> None:
    with pytest.raises(LlmOutputError, match=problem):
        parse_llm_json(reply)


def test_parse_refuses_an_oversized_reply_before_reading_it() -> None:
    with pytest.raises(LlmOutputError, match="over"):
        parse_llm_json("{" + " " * MAX_REPLY_CHARS + "}")


async def test_valid_reply_passes_without_repair() -> None:
    repair = RepairRecorder('{"results": {}}')
    output = await validate_llm_output(
        '{"results": {"a": 1}}', Scores, repair=repair, repair_enabled=True
    )
    assert output.value == Scores(results={"a": 1})
    assert not output.repaired
    assert repair.calls == []


async def test_invalid_reply_raises_when_repair_is_off_by_default() -> None:
    repair = RepairRecorder('{"results": {"a": 1}}')
    with pytest.raises(LlmOutputError, match="results"):
        await validate_llm_output('{"scores": {}}', Scores, repair=repair)
    assert repair.calls == []


async def test_repair_is_tried_once_and_told_what_failed() -> None:
    repair = RepairRecorder('{"results": {"a": 2}}')
    output = await validate_llm_output(
        '{"results": {"a": "high"}}', Scores, repair=repair, repair_enabled=True
    )
    assert output.repaired
    assert output.value == Scores(results={"a": 2})
    assert output.reply == '{"results": {"a": 2}}'
    [(rejected, problem)] = repair.calls
    assert rejected == '{"results": {"a": "high"}}'
    assert "results.a" in problem
    assert "high" not in problem  # the failing value is not quoted back


async def test_a_failed_repair_raises_without_a_second_repair() -> None:
    repair = RepairRecorder("still not json")
    with pytest.raises(LlmOutputError, match="repair answer failed too"):
        await validate_llm_output("nope", Scores, repair=repair, repair_enabled=True)
    assert len(repair.calls) == 1


async def test_repair_enabled_without_a_repair_call_raises_the_first_error() -> None:
    with pytest.raises(LlmOutputError, match="no JSON object"):
        await validate_llm_output("nope", Scores, repair_enabled=True)
