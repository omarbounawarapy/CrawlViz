"""Tests for pipelines/base_pipeline.py -- the shared queue/worker/
start/stop lifecycle introduced to fix two classes of bug found in the
engineering audit: StoragePipeline/RetryProcessor silently bypassing
their own queue (making `worker()`/`max_concurrency` dead code), and
most other pipelines having no reliable way to stop a worker blocked on
an empty queue once a crawl ends.
"""
import asyncio

import pytest

from pipelines.base_pipeline import SHUTDOWN, BasePipeline


class EchoPipeline(BasePipeline):
    """Minimal concrete BasePipeline: records everything it processes."""

    def __init__(self, max_concurrency: int = 1):
        super().__init__(max_concurrency=max_concurrency)
        self.queue: asyncio.Queue = asyncio.Queue()
        self.processed: list = []

    async def _process(self, item, worker_id: int) -> None:
        self.processed.append((item, worker_id))


class RaisingPipeline(BasePipeline):
    """A pipeline whose _process always raises, to prove BasePipeline's
    worker loop survives a bad item instead of dying silently.
    """

    def __init__(self):
        super().__init__(max_concurrency=1)
        self.queue: asyncio.Queue = asyncio.Queue()
        self.processed: list = []

    async def _process(self, item, worker_id: int) -> None:
        if item == "boom":
            raise ValueError("simulated failure")
        self.processed.append(item)


@pytest.mark.asyncio
async def test_put_enqueues_and_worker_processes_it():
    p = EchoPipeline()
    task = asyncio.create_task(p.start())
    await p.put("hello")
    await asyncio.sleep(0.02)
    await p.stop()
    await asyncio.wait_for(task, timeout=1.0)
    assert p.processed == [("hello", 0)]


@pytest.mark.asyncio
async def test_stop_wakes_a_worker_blocked_on_empty_queue():
    """The actual regression this class exists to prevent: a worker
    sitting on `await self.queue.get()` with nothing coming must still
    be woken by stop(), not hang forever.
    """
    p = EchoPipeline()
    task = asyncio.create_task(p.start())
    await asyncio.sleep(0.02)  # let the worker block on the empty queue

    await asyncio.wait_for(p.stop(), timeout=1.0)
    await asyncio.wait_for(task, timeout=1.0)  # would hang forever pre-fix


@pytest.mark.asyncio
async def test_stop_wakes_every_worker_at_higher_concurrency():
    p = EchoPipeline(max_concurrency=5)
    task = asyncio.create_task(p.start())
    await asyncio.sleep(0.02)
    await p.stop()
    await asyncio.wait_for(task, timeout=1.0)  # all 5 workers must exit


@pytest.mark.asyncio
async def test_worker_exception_does_not_kill_the_loop():
    p = RaisingPipeline()
    task = asyncio.create_task(p.start())
    await p.put("boom")
    await p.put("still alive")
    await asyncio.sleep(0.02)
    await p.stop()
    await asyncio.wait_for(task, timeout=1.0)
    assert p.processed == ["still alive"]


@pytest.mark.asyncio
async def test_process_not_implemented_by_default():
    p = BasePipeline(max_concurrency=1)
    p.queue = asyncio.Queue()
    with pytest.raises(NotImplementedError):
        await p._process("x", 0)


@pytest.mark.asyncio
async def test_max_concurrency_actually_bounds_worker_count():
    p = EchoPipeline(max_concurrency=3)
    task = asyncio.create_task(p.start())
    await asyncio.sleep(0.01)
    assert len(p.workers) == 3
    await p.stop()
    await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.asyncio
async def test_shutdown_sentinel_is_never_passed_to_process():
    """SHUTDOWN must be intercepted by the worker loop itself -- a
    subclass's _process() should never see it.
    """
    p = EchoPipeline()
    task = asyncio.create_task(p.start())
    await p.queue.put(SHUTDOWN)  # simulate what stop() does
    await asyncio.wait_for(task, timeout=1.0)
    assert p.processed == []
