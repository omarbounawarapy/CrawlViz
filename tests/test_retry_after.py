"""A failed response's Retry-After holds the whole host off, and the failure keeps its status."""

import asyncio
import email.utils
from typing import Any

import aiohttp
import pytest
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from crawlviz.events import RequestFailedEvent
from crawlviz.shared import Domain, Node
from pipelines.fetch_stage import FetchStage, is_rate_limited
from pipelines.http_failure import MAX_RETRY_AFTER_SECONDS, retry_after_seconds, status_of

HOST = "slow.test"
RETRY_AFTER_SECONDS = 120.0
# A fixed clock keeps the HTTP-date cases exact.
NOW = 1_800_000_000.0
DATE_OFFSET_SECONDS = 30
HTTP_TOO_MANY_REQUESTS = 429
HTTP_NOT_FOUND = 404
HTTP_SERVICE_UNAVAILABLE = 503
# The pipeline's own pacing is off in these tests, so only the hold-off remains.
NO_DELAY = 0.0
# How much of the hold-off must still be left right after the failure.
MINIMUM_REMAINING = RETRY_AFTER_SECONDS - 5


def failure(status: int, retry_after: str | None = None) -> aiohttp.ClientResponseError:
    info = aiohttp.RequestInfo(
        URL("http://x"), "GET", CIMultiDictProxy(CIMultiDict()), URL("http://x")
    )
    headers = CIMultiDict[str]()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return aiohttp.ClientResponseError(info, (), status=status, headers=CIMultiDictProxy(headers))


def test_seconds_are_read_as_given() -> None:
    assert retry_after_seconds(failure(HTTP_TOO_MANY_REQUESTS, "7")) == 7.0


def test_http_date_is_read_relative_to_now() -> None:
    date = email.utils.formatdate(NOW + DATE_OFFSET_SECONDS, usegmt=True)
    assert retry_after_seconds(failure(HTTP_TOO_MANY_REQUESTS, date), now=NOW) == float(
        DATE_OFFSET_SECONDS
    )


def test_a_date_in_the_past_means_no_wait() -> None:
    date = email.utils.formatdate(NOW - DATE_OFFSET_SECONDS, usegmt=True)
    assert retry_after_seconds(failure(HTTP_TOO_MANY_REQUESTS, date), now=NOW) == 0.0


def test_a_long_wait_is_capped() -> None:
    too_long = str(int(MAX_RETRY_AFTER_SECONDS) * 100)
    assert retry_after_seconds(failure(HTTP_TOO_MANY_REQUESTS, too_long)) == (
        MAX_RETRY_AFTER_SECONDS
    )


@pytest.mark.parametrize("value", [None, "", "soon", "-5", "²", "١٢"])
def test_missing_or_unreadable_header_gives_no_wait(value: str | None) -> None:
    assert retry_after_seconds(failure(HTTP_TOO_MANY_REQUESTS, value)) is None


def test_a_failure_without_a_response_has_no_wait_and_no_status() -> None:
    error = TimeoutError("no answer")
    assert retry_after_seconds(error) is None
    assert status_of(error) is None


class RecordingBroker:
    def __init__(self) -> None:
        self.failures: list[RequestFailedEvent] = []

    async def emit(self, event: object) -> None:
        if isinstance(event, RequestFailedEvent):
            self.failures.append(event)


class RefusingFetcher:
    """Answers every request with the given failure."""

    def __init__(self, error: aiohttp.ClientResponseError) -> None:
        self.error = error

    async def emit_request(self, params: dict[str, Any]) -> str:
        raise self.error

    async def close(self) -> None:
        pass


async def fail_one_fetch(
    error: aiohttp.ClientResponseError,
) -> tuple[FetchStage, RecordingBroker]:
    broker = RecordingBroker()
    pipeline = FetchStage(
        broker,
        max_concurrency=1,
        fetcher=RefusingFetcher(error),
        min_delay=NO_DELAY,
        jitter_max=NO_DELAY,
    )
    domain = Domain("test", f"http://{HOST}", ".//a")
    await pipeline.queue.put(Node(0, url=f"http://{HOST}/p0", domain=domain))
    task = asyncio.create_task(pipeline.start())
    while not broker.failures:
        await asyncio.sleep(0)
    await pipeline.stop()
    await task
    return pipeline, broker


async def test_retry_after_holds_the_host_off() -> None:
    pipeline, _ = await fail_one_fetch(
        failure(HTTP_TOO_MANY_REQUESTS, str(int(RETRY_AFTER_SECONDS)))
    )
    assert pipeline.pacer.reserve(HOST, spacing=NO_DELAY) > MINIMUM_REMAINING


async def test_a_failure_without_retry_after_leaves_the_host_free() -> None:
    pipeline, _ = await fail_one_fetch(failure(HTTP_TOO_MANY_REQUESTS))
    assert pipeline.pacer.reserve(HOST, spacing=NO_DELAY) < MINIMUM_REMAINING


async def test_the_failure_event_carries_the_http_status() -> None:
    _, broker = await fail_one_fetch(failure(HTTP_NOT_FOUND))
    assert broker.failures[0].status_code == HTTP_NOT_FOUND


@pytest.mark.parametrize(
    ("status", "expected"),
    [(HTTP_TOO_MANY_REQUESTS, True), (HTTP_SERVICE_UNAVAILABLE, True), (HTTP_NOT_FOUND, False)],
)
def test_429_and_503_are_slow_down_answers(status: int, expected: bool) -> None:
    assert is_rate_limited(failure(status)) is expected


def test_a_failure_without_a_response_is_not_a_slow_down() -> None:
    assert not is_rate_limited(TimeoutError("no answer"))
