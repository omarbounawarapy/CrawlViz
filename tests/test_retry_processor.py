"""RetryProcessor: scoring failures are rescheduled, and fetch retries are delayed."""
import asyncio

from events import RequestFailedEvent, ScoreRescheduledEvent, ScoringFailedEvent
from pipelines.retry_processor import RetryProcessor


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
    rp = RetryProcessor(None, broker, requests_pipeline=reqs, retry_base_delay=0.01, **kw)
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
        RequestFailedEvent(
            correlation_id="1", node=node, error_type="E", error_message="502"
        ),
        0,
    )
    assert reqs.queue.empty()
    await asyncio.gather(*rp._pending)
    assert reqs.queue.get_nowait() is node
