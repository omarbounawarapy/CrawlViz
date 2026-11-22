"""The benchmark judges accept only the label type their prompt asks for."""

from typing import Any

import pytest

from benchmark import judge as graded_judge
from benchmark import label as binary_judge
from models.llm_context import LlmContext


class ScriptedSender:
    """Answers each call with the next scripted answer and keeps the prompts it was sent."""

    def __init__(self, answers: list[dict[str, Any]]) -> None:  # Any: provider JSON
        self.answers = list(answers)
        self.prompts: list[str] = []

    async def send(self, context: LlmContext) -> dict[str, Any]:  # Any: provider JSON
        self.prompts.append(context.prompt)
        return self.answers.pop(0)


ROWS = [
    {"id": "a", "title": "Page A", "excerpt": "about the topic"},
    {"id": "b", "title": "Page B", "excerpt": "about something else"},
]
BATCH = [
    ("a", {"title": "Page A", "text": "about the topic"}),
    ("b", {"title": "Page B", "text": "about something else"}),
]


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(graded_judge, "BACKOFF_SECONDS", 0)
    monkeypatch.setattr(binary_judge, "BACKOFF_SECONDS", 0)


@pytest.mark.parametrize("value", [0, 1, 2])
def test_a_grade_is_the_integer_0_1_or_2(value: int) -> None:
    assert graded_judge.as_grade(value) == value


@pytest.mark.parametrize("value", [True, False, "2", 2.0, 3, -1, None, [1]])
def test_booleans_strings_floats_and_out_of_range_values_are_not_grades(value: object) -> None:
    assert graded_judge.as_grade(value) is None


async def test_graded_judge_retries_an_answer_given_as_true_and_false() -> None:
    sender = ScriptedSender([{"labels": {"1": True, "2": False}}, {"labels": {"1": 2, "2": 0}}])
    labels = await graded_judge.judge(sender, ROWS)
    assert labels == {"a": 2, "b": 0}
    assert all(type(grade) is int for grade in labels.values())
    assert len(sender.prompts) == 2
    assert sender.prompts[0] != sender.prompts[1]


async def test_graded_judge_gives_up_when_every_answer_uses_booleans() -> None:
    sender = ScriptedSender([{"labels": {"1": True, "2": True}}] * graded_judge.MAX_ATTEMPTS)
    with pytest.raises(RuntimeError, match="no usable answer"):
        await graded_judge.judge(sender, ROWS)
    assert len(sender.prompts) == graded_judge.MAX_ATTEMPTS


@pytest.mark.parametrize("result", [{}, {"labels": [0, 1]}, {"labels": "0,1"}, [], None])
def test_an_answer_without_a_label_map_has_no_labels(result: object) -> None:
    assert binary_judge.answer_labels(result) == {}


@pytest.mark.parametrize("value", [True, False])
def test_a_binary_label_is_json_true_or_false(value: bool) -> None:
    assert binary_judge.as_binary_label(value) is value


@pytest.mark.parametrize("value", ["false", "no", "true", 0, 1, None])
def test_strings_and_numbers_are_not_binary_labels(value: object) -> None:
    assert binary_judge.as_binary_label(value) is None


async def test_binary_judge_does_not_read_the_string_false_as_relevant() -> None:
    sender = ScriptedSender(
        [{"labels": {"1": "false", "2": "no"}}, {"labels": {"1": True, "2": False}}]
    )
    labels = await binary_judge.judge(sender, "topic", BATCH)
    assert labels == {"a": True, "b": False}
    assert len(sender.prompts) == 2


async def test_binary_judge_gives_up_when_no_answer_uses_booleans() -> None:
    sender = ScriptedSender([{"labels": {"1": "yes", "2": "no"}}] * binary_judge.MAX_ATTEMPTS)
    with pytest.raises(RuntimeError, match="no usable answer"):
        await binary_judge.judge(sender, "topic", BATCH)
