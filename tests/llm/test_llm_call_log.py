"""LlmHandler records every call it makes through an `LlmCallLog`, answered or failed."""

import asyncio
import json
from pathlib import Path

import aiohttp
import pytest

from crawlviz.llm import (
    LLM_CALLS_FILE_NAME,
    CallOutcome,
    KeyManager,
    LlmCallRecorder,
    LlmHandler,
    LlmTimeoutError,
)
from crawlviz.llm.call_log import UNKNOWN_MODEL, LlmCallLog
from crawlviz.llm.prompt_registry import hash_messages
from crawlviz.llm.types import ChatRole, LlmMessage
from crawlviz.shared import set_trace
from models import ScoringContext

PROVIDER = "openai"
MODEL = "model-x"
PROMPT = "page text"
SECRET_KEY = "sk-test-secret-key-0123456789"
SHORT_TIMEOUT_SECONDS = 0.05
INPUT_TOKENS = 120
OUTPUT_TOKENS = 30


def _reply(content: str) -> dict[str, object]:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": INPUT_TOKENS, "completion_tokens": OUTPUT_TOKENS},
    }


class ScriptedClient:
    """A network client that gives each request the next scripted answer or error."""

    def __init__(self, *answers: object) -> None:
        self.answers = list(answers)

    async def emit_request(self, params: dict[str, object]) -> object:
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        if answer is None:
            await asyncio.Event().wait()
        return answer


def _http_error(status: int) -> aiohttp.ClientResponseError:
    return aiohttp.ClientResponseError(None, (), status=status)  # type: ignore[arg-type]


@pytest.fixture
def key_manager(monkeypatch: pytest.MonkeyPatch) -> KeyManager:
    monkeypatch.setattr(KeyManager, "load_keys", lambda self: {PROVIDER: [SECRET_KEY]})
    return KeyManager(keys_file=Path("unused-keys.json"))


@pytest.fixture
def calls_file(tmp_path: Path) -> Path:
    return tmp_path / LLM_CALLS_FILE_NAME


def _handler(key_manager: KeyManager, calls_file: Path, *answers: object) -> LlmHandler:
    handler = LlmHandler(
        key_manager, client=ScriptedClient(*answers), temperature=0.2, max_tokens=256
    )
    handler.call_log = LlmCallLog(LlmCallRecorder(calls_file, store_text=True))
    return handler


def _records(calls_file: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in calls_file.read_text().splitlines()]


async def test_an_answered_call_is_recorded_with_its_tokens_and_request(
    key_manager: KeyManager, calls_file: Path
) -> None:
    handler = _handler(key_manager, calls_file, _reply('{"results": {"a": 1}}'))

    async def send_in_a_traced_task() -> dict[str, object]:
        set_trace("trace-1", "node-1")  # bound in this task only, so no other test sees it
        return await handler.send(ScoringContext(PROVIDER, MODEL, PROMPT))

    assert await asyncio.create_task(send_in_a_traced_task()) == {"results": {"a": 1}}

    [record] = _records(calls_file)
    assert record["outcome"] == CallOutcome.OK
    assert (record["provider"], record["model"]) == (PROVIDER, MODEL)
    assert (record["input_tokens"], record["output_tokens"]) == (INPUT_TOKENS, OUTPUT_TOKENS)
    assert record["attempts"] == 1
    assert record["temperature"] == 0.2
    assert (record["trace_id"], record["node_id"]) == ("trace-1", "node-1")
    assert json.loads(str(record["raw_reply"])) == {"results": {"a": 1}}
    expected_hash = hash_messages((LlmMessage(role=ChatRole.USER, content=PROMPT),))
    assert record["prompt_hash"] == expected_hash
    assert record["rendered_prompt"] == f"[user]\n{PROMPT}"


async def test_the_prompt_and_reply_text_are_left_out_unless_asked_for(
    key_manager: KeyManager, calls_file: Path
) -> None:
    handler = LlmHandler(key_manager, client=ScriptedClient(_reply('{"results": {}}')))
    handler.call_log = LlmCallLog(LlmCallRecorder(calls_file))

    await handler.send(ScoringContext(PROVIDER, MODEL, PROMPT))

    [record] = _records(calls_file)
    assert (record["rendered_prompt"], record["raw_reply"]) == (None, None)


async def test_an_unreadable_reply_is_recorded_as_invalid_output(
    key_manager: KeyManager, calls_file: Path
) -> None:
    handler = _handler(key_manager, calls_file, _reply("not json"))

    assert await handler.send(ScoringContext(PROVIDER, MODEL, PROMPT)) == {}

    [record] = _records(calls_file)
    assert record["outcome"] == CallOutcome.INVALID_OUTPUT


async def test_a_refused_call_is_recorded_with_its_status_and_reraised(
    key_manager: KeyManager, calls_file: Path
) -> None:
    handler = _handler(key_manager, calls_file, _http_error(400))

    with pytest.raises(aiohttp.ClientResponseError):
        await handler.send(ScoringContext(PROVIDER, MODEL, PROMPT))

    [record] = _records(calls_file)
    assert record["outcome"] == CallOutcome.HTTP_ERROR
    assert record["error"] == f"LLM {PROVIDER}/{MODEL} answered HTTP 400"
    assert SECRET_KEY not in calls_file.read_text()


async def test_an_unreachable_provider_is_recorded_as_a_network_error(
    key_manager: KeyManager, calls_file: Path
) -> None:
    handler = _handler(key_manager, calls_file, aiohttp.ClientConnectionError("refused"))

    with pytest.raises(aiohttp.ClientConnectionError):
        await handler.send(ScoringContext(PROVIDER, MODEL, PROMPT))

    [record] = _records(calls_file)
    assert record["outcome"] == CallOutcome.NETWORK_ERROR


async def test_a_timeout_is_recorded_with_the_attempts_it_took(
    key_manager: KeyManager, calls_file: Path
) -> None:
    handler = _handler(key_manager, calls_file, None)
    handler.timeout_seconds = SHORT_TIMEOUT_SECONDS

    with pytest.raises(LlmTimeoutError):
        await handler.send(ScoringContext(PROVIDER, MODEL, PROMPT))

    [record] = _records(calls_file)
    assert record["outcome"] == CallOutcome.TIMEOUT
    assert record["attempts"] == 1
    assert float(str(record["latency_ms"])) >= SHORT_TIMEOUT_SECONDS * 1000


async def test_a_context_without_a_model_is_still_recorded(
    key_manager: KeyManager, calls_file: Path
) -> None:
    handler = _handler(key_manager, calls_file, _reply('{"results": {}}'))

    await handler.send(ScoringContext(PROVIDER, "", PROMPT))

    [record] = _records(calls_file)
    assert record["model"] == UNKNOWN_MODEL


async def test_without_a_call_log_nothing_is_recorded(
    key_manager: KeyManager, calls_file: Path
) -> None:
    handler = LlmHandler(key_manager, client=ScriptedClient(_reply('{"results": {}}')))

    assert await handler.send(ScoringContext(PROVIDER, MODEL, PROMPT)) == {"results": {}}
    assert not calls_file.exists()
