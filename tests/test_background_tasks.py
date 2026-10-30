"""Background tasks are held while they run, logged when they fail, and cancelled on demand."""

import asyncio
import logging

from utils import BackgroundTasks


async def test_task_is_held_until_it_ends():
    tasks = BackgroundTasks()
    gate = asyncio.Event()

    async def wait_for_gate():
        await gate.wait()

    task = tasks.spawn(wait_for_gate(), name="waiter")
    assert len(tasks) == 1 and list(tasks) == [task]
    gate.set()
    await task
    await asyncio.sleep(0)  # the done callback runs on the next loop turn
    assert len(tasks) == 0


async def test_failure_is_logged_with_the_task_name(caplog):
    tasks = BackgroundTasks()

    async def explode():
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR, logger="utils.background_tasks"):
        task = tasks.spawn(explode(), name="export-batch-completed")
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)

    assert any("export-batch-completed" in record.getMessage() for record in caplog.records)
    assert len(tasks) == 0


async def test_cancel_all_ends_running_tasks_without_logging_an_error(caplog):
    tasks = BackgroundTasks()

    async def sleep_forever():
        await asyncio.sleep(3600)

    running = tasks.spawn(sleep_forever(), name="sleeper")
    with caplog.at_level(logging.ERROR, logger="utils.background_tasks"):
        await tasks.cancel_all()
    assert running.cancelled() and len(tasks) == 0
    assert not caplog.records
