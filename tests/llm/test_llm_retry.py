"""LlmHandler retries a provider's 429 and 5xx answers, and nothing else.

A real aiohttp server stands in for the provider, so the errors come out of the
real NetworkClient with real headers. Sleeps are recorded instead of waited.
"""

from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import aiohttp
import pytest
from aiohttp import test_utils, web

from crawlviz.llm import KeyManager, LlmHandler
from crawlviz.llm.llm_handler import RetryPolicy, parse_retry_after
from crawlviz.shared import NetworkClient
from models import ScoringContext

PROVIDER = "openai"
SECRET_KEY = "sk-test-secret-key-0123456789"
ANSWER = {"choices": [{"message": {"content": '{"results": {"a": 1}}'}}]}
PARSED_ANSWER = {"results": {"a": 1}}


class ScriptedProvider:
    """Answers each request with the next scripted (status, headers) pair, then 200."""

    def __init__(self, script: list[tuple[int, dict[str, str]]]) -> None:
        self.script: Iterator[tuple[int, dict[str, str]]] = iter(script)
        self.requests = 0
        self.keys: list[str] = []

    async def handle(self, request: web.Request) -> web.Response:
        self.requests += 1
        self.keys.append(request.headers["Authorization"].removeprefix("Bearer "))
        status, headers = next(self.script, (200, {}))
        if status == 200:
            return web.json_response(ANSWER)
        return web.json_response({"error": "scripted"}, status=status, headers=headers)


class SleepRecorder:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


@pytest.fixture
def key_manager(monkeypatch: pytest.MonkeyPatch) -> KeyManager:
    monkeypatch.setattr(KeyManager, "load_keys", lambda self: {PROVIDER: [SECRET_KEY]})
    return KeyManager(keys_file=Path("unused-keys.json"))


@pytest.fixture
async def network() -> AsyncIterator[NetworkClient]:
    client = NetworkClient(allow_private_addresses=True)  # the scripted provider is on loopback
    yield client
    await client.close()


async def start(provider: ScriptedProvider) -> test_utils.TestServer:
    app = web.Application()
    app.router.add_post("/v1/chat/completions", provider.handle)
    server = test_utils.TestServer(app)
    await server.start_server()
    return server


async def send(
    provider: ScriptedProvider,
    key_manager: KeyManager,
    network: NetworkClient,
    sleep: SleepRecorder,
    policy: RetryPolicy | None = None,
) -> dict[str, object]:
    server = await start(provider)
    try:
        handler = LlmHandler(
            key_manager,
            client=network,
            endpoints={PROVIDER: str(server.make_url("/v1/chat/completions"))},
        )
        handler.retry_policy = replace(policy or LlmHandler.retry_policy, sleep=sleep)
        return await handler.send(ScoringContext(PROVIDER, "model-x", "prompt"))
    finally:
        await server.close()


async def test_429_waits_the_retry_after_seconds_then_succeeds(
    key_manager: KeyManager, network: NetworkClient
) -> None:
    provider = ScriptedProvider([(429, {"Retry-After": "2"})])
    sleep = SleepRecorder()

    assert await send(provider, key_manager, network, sleep) == PARSED_ANSWER
    assert sleep.delays == [2.0]
    assert provider.requests == 2


async def test_5xx_without_retry_after_backs_off_exponentially(
    key_manager: KeyManager, network: NetworkClient
) -> None:
    provider = ScriptedProvider([(503, {}), (500, {}), (502, {})])
    sleep = SleepRecorder()
    policy = RetryPolicy(max_retries=3, base_delay_seconds=1.0, backoff_factor=2.0)

    assert await send(provider, key_manager, network, sleep, policy) == PARSED_ANSWER
    assert sleep.delays == [1.0, 2.0, 4.0]
    assert provider.requests == 4


async def test_backoff_never_exceeds_the_max_delay(
    key_manager: KeyManager, network: NetworkClient
) -> None:
    provider = ScriptedProvider([(500, {})] * 3)
    sleep = SleepRecorder()
    policy = RetryPolicy(
        max_retries=3, base_delay_seconds=10.0, backoff_factor=10.0, max_delay_seconds=15.0
    )

    await send(provider, key_manager, network, sleep, policy)
    assert sleep.delays == [10.0, 15.0, 15.0]


async def test_attempts_are_bounded_and_the_last_error_is_raised(
    key_manager: KeyManager, network: NetworkClient
) -> None:
    provider = ScriptedProvider([(503, {})] * 10)
    sleep = SleepRecorder()
    policy = RetryPolicy(max_retries=2)

    with pytest.raises(aiohttp.ClientResponseError) as raised:
        await send(provider, key_manager, network, sleep, policy)
    assert raised.value.status == 503
    assert provider.requests == 3
    assert len(sleep.delays) == 2


@pytest.mark.parametrize("status", [400, 404, 408, 422])
async def test_other_4xx_is_raised_at_once(
    status: int, key_manager: KeyManager, network: NetworkClient
) -> None:
    provider = ScriptedProvider([(status, {"Retry-After": "1"})])
    sleep = SleepRecorder()

    with pytest.raises(aiohttp.ClientResponseError) as raised:
        await send(provider, key_manager, network, sleep)
    assert raised.value.status == status
    assert provider.requests == 1
    assert sleep.delays == []


async def test_retry_after_above_the_max_delay_is_raised_not_shortened(
    key_manager: KeyManager, network: NetworkClient
) -> None:
    provider = ScriptedProvider([(429, {"Retry-After": "1900"})])
    sleep = SleepRecorder()

    with pytest.raises(aiohttp.ClientResponseError) as raised:
        await send(provider, key_manager, network, sleep, RetryPolicy(max_delay_seconds=30.0))
    assert raised.value.status == 429
    assert provider.requests == 1
    assert sleep.delays == []


async def test_retry_after_as_an_http_date_is_honoured(
    key_manager: KeyManager, network: NetworkClient
) -> None:
    when = format_datetime(datetime.now(UTC) + timedelta(seconds=20), usegmt=True)
    provider = ScriptedProvider([(503, {"Retry-After": when})])
    sleep = SleepRecorder()

    await send(provider, key_manager, network, sleep)
    assert len(sleep.delays) == 1
    assert 15.0 < sleep.delays[0] <= 20.0


async def test_a_retry_moves_to_the_next_key(
    monkeypatch: pytest.MonkeyPatch, network: NetworkClient
) -> None:
    monkeypatch.setattr(KeyManager, "load_keys", lambda self: {PROVIDER: ["key-a", "key-b"]})
    provider = ScriptedProvider([(429, {})])

    await send(provider, KeyManager(keys_file=Path("unused-keys.json")), network, SleepRecorder())
    assert provider.keys == ["key-a", "key-b"]


async def test_zero_retries_turns_retrying_off(
    key_manager: KeyManager, network: NetworkClient
) -> None:
    provider = ScriptedProvider([(429, {"Retry-After": "1"})])
    sleep = SleepRecorder()

    with pytest.raises(aiohttp.ClientResponseError):
        await send(provider, key_manager, network, sleep, RetryPolicy(max_retries=0))
    assert provider.requests == 1
    assert sleep.delays == []


async def test_each_retry_is_logged_with_context_and_without_the_key(
    key_manager: KeyManager, network: NetworkClient, caplog: pytest.LogCaptureFixture
) -> None:
    provider = ScriptedProvider([(429, {"Retry-After": "3"}), (503, {})] + [(503, {})] * 5)
    sleep = SleepRecorder()

    with (
        caplog.at_level("WARNING", logger="crawlviz.llm.llm_handler"),
        pytest.raises(aiohttp.ClientResponseError),
    ):
        await send(provider, key_manager, network, sleep, RetryPolicy(max_retries=2))

    messages = [r.getMessage() for r in caplog.records if r.name == "crawlviz.llm.llm_handler"]
    assert len(messages) == 3  # two retries, then giving up
    assert "openai" in messages[0] and "model-x" in messages[0]
    assert "429" in messages[0] and "retry 1 of 2" in messages[0] and "Retry-After" in messages[0]
    assert "503" in messages[1] and "retry 2 of 2" in messages[1]
    assert "giving up" in messages[2]
    assert SECRET_KEY not in caplog.text
    assert SECRET_KEY[-8:] not in caplog.text


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, None),
        ("", None),
        ("0", 0.0),
        ("7", 7.0),
        (" 1.5 ", 1.5),
        ("-3", None),
        ("nan", None),
        ("inf", None),
        ("soon", None),
        ("Wed, 21 Oct 2015 07:28:00 GMT", 0.0),  # a date in the past means now
    ],
)
def test_parse_retry_after(header: str | None, expected: float | None) -> None:
    assert parse_retry_after(header) == expected


def test_parse_retry_after_reads_a_future_http_date() -> None:
    now = datetime(2026, 10, 30, 12, 0, 0, tzinfo=UTC)
    assert parse_retry_after("Fri, 30 Oct 2026 12:00:45 GMT", now=now) == 45.0


@pytest.mark.parametrize(
    "make_policy",
    [
        lambda: RetryPolicy(max_retries=-1),
        lambda: RetryPolicy(base_delay_seconds=-1.0),
        lambda: RetryPolicy(max_delay_seconds=-1.0),
        lambda: RetryPolicy(backoff_factor=0.5),
    ],
)
def test_a_policy_that_would_not_be_bounded_is_refused(
    make_policy: Callable[[], RetryPolicy],
) -> None:
    with pytest.raises(ValueError, match="must"):
        make_policy()
