"""LlmHandler gives up on an attempt that gets no answer within its timeout."""

import asyncio
import logging
from pathlib import Path

import aiohttp
import pytest

from crawlviz.llm import CallOutcome, KeyManager, LlmHandler, LlmTimeoutError, RetryPolicy
from crawlviz.llm.llm_handler import DEFAULT_TIMEOUT_SECONDS
from models import ScoringContext

PROVIDER = "openai"
SECRET_KEY = "sk-test-secret-key-0123456789"
SHORT_TIMEOUT_SECONDS = 0.05
OK_REPLY: dict[str, object] = {"choices": [{"message": {"content": '{"results": {}}'}}]}


async def _no_wait(seconds: float) -> None:
    return None


class SilentProvider:
    """A network client whose provider never answers, after `busy_answers` 429s."""

    def __init__(self, busy_answers: int = 0) -> None:
        self.requests = 0
        self.busy_answers = busy_answers

    async def emit_request(self, params: dict[str, object]) -> dict[str, object]:
        self.requests += 1
        if self.requests <= self.busy_answers:
            raise aiohttp.ClientResponseError(None, (), status=429)  # type: ignore[arg-type]
        await asyncio.Event().wait()
        raise AssertionError("unreachable: the event is never set")


class TimingOutClient:
    """A network client whose own timeout fires first."""

    async def emit_request(self, params: dict[str, object]) -> dict[str, object]:
        raise TimeoutError


class AnsweringClient:
    async def emit_request(self, params: dict[str, object]) -> dict[str, object]:
        return OK_REPLY


@pytest.fixture
def key_manager(monkeypatch: pytest.MonkeyPatch) -> KeyManager:
    monkeypatch.setattr(KeyManager, "load_keys", lambda self: {PROVIDER: [SECRET_KEY]})
    return KeyManager(keys_file=Path("unused-keys.json"))


async def test_an_attempt_without_an_answer_ends_as_a_typed_timeout(
    key_manager: KeyManager, caplog: pytest.LogCaptureFixture
) -> None:
    client = SilentProvider()
    handler = LlmHandler(key_manager, client=client)
    handler.timeout_seconds = SHORT_TIMEOUT_SECONDS

    with (
        caplog.at_level(logging.WARNING, logger="crawlviz.llm.llm_handler"),
        pytest.raises(LlmTimeoutError) as raised,
    ):
        await handler.send(ScoringContext(PROVIDER, "model-x", "prompt"))

    assert client.requests == 1  # a timeout is not retried
    error = raised.value
    assert error.outcome is CallOutcome.TIMEOUT
    assert error.attempts == 1
    assert error.latency_ms >= SHORT_TIMEOUT_SECONDS * 1000
    assert str(error) == "LLM openai/model-x gave no answer within 0.05 s"
    [warning] = [r.getMessage() for r in caplog.records]
    assert "openai/model-x gave no answer within 0.05 s" in warning
    assert SECRET_KEY not in warning


async def test_the_timeout_counts_the_retries_before_it(key_manager: KeyManager) -> None:
    handler = LlmHandler(key_manager, client=SilentProvider(busy_answers=2))
    handler.timeout_seconds = SHORT_TIMEOUT_SECONDS
    handler.retry_policy = RetryPolicy(sleep=_no_wait)

    with pytest.raises(LlmTimeoutError) as raised:
        await handler.send(ScoringContext(PROVIDER, "model-x", "prompt"))

    assert raised.value.attempts == 3  # two 429 answers, then no answer


async def test_the_client_timeout_is_reported_as_the_clients(
    key_manager: KeyManager, caplog: pytest.LogCaptureFixture
) -> None:
    handler = LlmHandler(key_manager, client=TimingOutClient())

    with (
        caplog.at_level(logging.WARNING, logger="crawlviz.llm.llm_handler"),
        pytest.raises(LlmTimeoutError, match="timed out in the network client"),
    ):
        await handler.send(ScoringContext(PROVIDER, "model-x", "prompt"))

    [warning] = [r.getMessage() for r in caplog.records]
    assert "openai/model-x timed out in the network client" in warning


async def test_a_timeout_is_still_a_timeout_error_for_older_callers(
    key_manager: KeyManager,
) -> None:
    with pytest.raises(TimeoutError):
        await LlmHandler(key_manager, client=TimingOutClient()).send(
            ScoringContext(PROVIDER, "model-x", "prompt")
        )


async def test_an_answer_in_time_is_returned(key_manager: KeyManager) -> None:
    handler = LlmHandler(key_manager, client=AnsweringClient())
    assert await handler.send(ScoringContext(PROVIDER, "model-x", "prompt")) == {"results": {}}


def test_the_default_timeout_is_the_named_constant(key_manager: KeyManager) -> None:
    assert LlmHandler(key_manager).timeout_seconds == DEFAULT_TIMEOUT_SECONDS


@pytest.mark.parametrize("timeout_seconds", [0.0, -1.0, float("nan"), float("inf")])
def test_a_timeout_that_is_not_a_positive_number_is_refused(
    key_manager: KeyManager, timeout_seconds: float
) -> None:
    handler = LlmHandler(key_manager)
    with pytest.raises(ValueError, match="timeout"):
        handler.timeout_seconds = timeout_seconds
    assert handler.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
