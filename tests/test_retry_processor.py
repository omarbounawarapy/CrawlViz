"""RetryStage: scoring failures are rescheduled, and fetch retries are delayed."""

import asyncio

from crawlviz.events import RequestFailedEvent, ScoreRescheduledEvent, ScoringFailedEvent
from pipelines.retry_stage import RetryStage


class FakeNode:
    def __init__(self, node_id=1):
        self.id = node_id

    def get_id(self):
        return self.id

    def decrease_priority(self, n):
        pass


class FakeBroker:
    def __init__(self):
        self.emitted = []

    async def emit(self, event):
        self.emitted.append(event)


class FakeRequests:
    def __init__(self):
        self.queue = asyncio.Queue()


def make(**kw):
    broker, reqs = FakeBroker(), FakeRequests()
    rp = RetryStage(None, broker, requests_pipeline=reqs, retry_base_delay=0.01, **kw)
    return rp, broker, reqs


def scoring_failed(node):
    return ScoringFailedEvent(
        correlation_id="1", node=node, stage="S", error_type="E", error_message="m"
    )


async def test_scoring_failure_is_rescheduled():
    rp, broker, _ = make()
    node = FakeNode()
    await rp._process(scoring_failed(node), 0)
    await asyncio.gather(*rp._pending)
    assert [type(e) for e in broker.emitted] == [ScoreRescheduledEvent]
    assert broker.emitted[0].node is node


async def test_scoring_failure_gives_up_after_max_retries():
    rp, broker, _ = make(max_scoring_retries=2)
    node = FakeNode()
    for _ in range(4):
        await rp._process(scoring_failed(node), 0)
    await asyncio.gather(*rp._pending)
    assert len(broker.emitted) == 2


async def test_request_retry_is_delayed_not_immediate():
    rp, _, reqs = make()
    node = FakeNode()
    await rp._process(
        RequestFailedEvent(correlation_id="1", node=node, error_type="E", error_message="502"),
        0,
    )
    assert reqs.queue.empty()
    await asyncio.gather(*rp._pending)
    assert reqs.queue.get_nowait() is node


class FailableNode(FakeNode):
    def __init__(self):
        super().__init__()
        self.failed = False

    def fail(self):
        self.failed = True


async def test_request_the_fetch_policy_refused_is_not_retried():
    refusals = ("BlockedAddressError", "ResponseTooLargeError", "UnsupportedContentTypeError")
    for error_type in refusals:
        rp, _, reqs = make()
        node = FailableNode()
        await rp._process(
            RequestFailedEvent(
                correlation_id="1", node=node, error_type=error_type, error_message="refused"
            ),
            0,
        )
        await asyncio.gather(*rp._pending)
        assert node.failed and reqs.queue.empty()


HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_GONE = 410
HTTP_REQUEST_TIMEOUT = 408
HTTP_TOO_MANY_REQUESTS = 429
HTTP_BAD_GATEWAY = 502


def http_failed(node: FailableNode, status: int | None) -> RequestFailedEvent:
    return RequestFailedEvent(
        correlation_id="1",
        node=node,
        error_type="ClientResponseError",
        error_message="m",
        status_code=status,
    )


async def test_permanent_client_errors_are_not_retried() -> None:
    for status in (HTTP_FORBIDDEN, HTTP_NOT_FOUND, HTTP_GONE):
        rp, _, reqs = make()
        node = FailableNode()
        await rp._process(http_failed(node, status), 0)
        await asyncio.gather(*rp._pending)
        assert node.failed
        assert reqs.queue.empty()


async def test_timeouts_and_rate_limits_and_server_errors_are_retried() -> None:
    for status in (HTTP_REQUEST_TIMEOUT, HTTP_TOO_MANY_REQUESTS, HTTP_BAD_GATEWAY, None):
        rp, _, reqs = make()
        node = FailableNode()
        await rp._process(http_failed(node, status), 0)
        await asyncio.gather(*rp._pending)
        assert not node.failed
        assert reqs.queue.get_nowait() is node
