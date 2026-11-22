"""Stopping a pipeline whose queue is full and whose workers are stuck must
return, not wait for room that never comes."""

import asyncio
from typing import Any

import pytest

from pipelines import base_pipeline
from pipelines.base_pipeline import BasePipeline

SHORT_TIMEOUT_SECONDS = 0.05
FINISH_WAIT_SECONDS = 5


class _StuckPipeline(BasePipeline):
    """One worker that never finishes its item, behind a queue of one."""

    def __init__(self) -> None:
        super().__init__(max_concurrency=1)
        self.queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=1)
        self.entered = asyncio.Event()

    async def _process(self, item: Any, worker_id: int) -> None:
        self.entered.set()
        await asyncio.Event().wait()


async def test_stop_on_a_full_queue_gives_up_after_a_timeout_and_ends_the_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(base_pipeline, "SHUTDOWN_PUT_TIMEOUT_SECONDS", SHORT_TIMEOUT_SECONDS)
    pipeline = _StuckPipeline()
    running = asyncio.create_task(pipeline.start())
    await pipeline.queue.put("first")
    await asyncio.wait_for(pipeline.entered.wait(), FINISH_WAIT_SECONDS)
    await pipeline.queue.put("second")  # the queue is now full

    await asyncio.wait_for(pipeline.stop(), FINISH_WAIT_SECONDS)
    await asyncio.wait_for(running, FINISH_WAIT_SECONDS)

    assert all(worker.done() for worker in pipeline.workers)


async def test_stop_on_a_queue_with_room_wakes_the_worker_without_waiting() -> None:
    pipeline = _StuckPipeline()
    pipeline._process = lambda item, worker_id: asyncio.sleep(0)  # type: ignore[method-assign]
    running = asyncio.create_task(pipeline.start())
    await asyncio.sleep(0)

    await asyncio.wait_for(pipeline.stop(), FINISH_WAIT_SECONDS)
    await asyncio.wait_for(running, FINISH_WAIT_SECONDS)
