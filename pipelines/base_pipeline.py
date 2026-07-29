import asyncio
import logging

logger = logging.getLogger(__name__)


class _ShutdownSentinel:
    """Pushed onto a pipeline's queue to wake a blocked worker for
    shutdown. A dedicated type (not None/object()) so it's unambiguous
    even for pipelines whose queue legitimately carries None-like items.

    Comparable against anything and always sorts first -- this is what
    lets it be pushed safely into an `asyncio.PriorityQueue` (e.g.
    ScoringPipeline's queue of bare Nodes, ProcessingPipeline's queue of
    (Node, content) tuples) without heapq raising when it compares this
    sentinel against a real queue item. Combined with Node.__lt__
    returning NotImplemented for non-Node operands (see models/node.py),
    both comparison directions resolve safely.
    """
    __slots__ = ()

    def __repr__(self) -> str:
        return "<pipeline-shutdown-sentinel>"

    def __lt__(self, other) -> bool:
        return True

    def __le__(self, other) -> bool:
        return True

    def __gt__(self, other) -> bool:
        return False

    def __ge__(self, other) -> bool:
        return False

    def __eq__(self, other) -> bool:
        return other is self

    def __hash__(self) -> int:
        return id(self)


SHUTDOWN = _ShutdownSentinel()


class BasePipeline:
    """Shared queue/worker/start/stop lifecycle for event-consuming pipelines.

    This exists because two pipelines (StoragePipeline, RetryProcessor)
    independently hand-rolled this exact scaffolding and both silently
    got it wrong -- `put()` bypassed `self.queue` entirely, making
    `worker()`/`max_concurrency` dead code. It also exists because most
    of the *other* pipelines had no reliable way to stop their worker
    loop: the common pattern was

        while self.event_broker.running:
            event = await self.queue.get()
            ...

    which only re-checks `running` *after* `queue.get()` unblocks. Once
    a crawl's stop conditions are met and no more events are coming, a
    pipeline sitting on an empty queue blocks forever -- which is
    exactly why `Crawler.start()`'s `asyncio.gather(*tasks)` wasn't
    reliably completing even after a crawl had genuinely finished (see
    `StoppingPipeline`, ironically, for a pipeline that could hang
    itself this way, and `nlp/space_updater.py`'s docstring for the
    same class of bug outside the pipeline system entirely).

    Subclasses:
        - set `self.queue` themselves in their own `__init__` (before or
          after calling `super().__init__()` -- order doesn't matter,
          `start()`/`stop()` only look at `self.queue` once running).
          Use `asyncio.Queue()` by default, or `asyncio.PriorityQueue()`
          where ordering matters (e.g. by node priority).
        - implement `async def _process(self, item, worker_id) -> None`
          with whatever previously lived inside their `worker()` loop's
          `try` block -- handler dispatch, emitting a completion event,
          catching a specific exception type to emit a specific
          `XFailedEvent`, etc. This is a mechanical extraction of
          existing behavior, not a rewrite of it: the loop, the sentinel
          check, and `task_done()` now live here instead.
        - may override `put()` for pre-processing before enqueueing
          (several pipelines emit an "enqueued" trace event first, or
          enqueue a derived work item rather than the raw event).

    `stop()` pushes one `SHUTDOWN` sentinel per worker so every worker
    wakes immediately instead of waiting for a real event that might
    never come, and exits cleanly. `EventBroker._shutdown()` calls this
    on every registered consumer once the crawl ends -- regardless of
    whether that particular pipeline is individually subscribed to
    StopCrawlEvent -- so this no longer needs to be wired by hand per
    pipeline.
    """

    def __init__(self, max_concurrency: int = 1):
        self.max_concurrency = max_concurrency
        self.workers: list[asyncio.Task] = []
        # Subclasses are expected to set self.queue themselves.

    async def put(self, event) -> None:
        await self.queue.put(event)

    async def start(self) -> None:
        self.workers = [
            asyncio.create_task(self._worker_loop(i))
            for i in range(self.max_concurrency)
        ]
        await asyncio.gather(*self.workers)

    async def stop(self) -> None:
        """Wake every worker so start() returns, even if the queue would
        otherwise sit empty forever. Safe to call more than once.
        """
        for _ in range(self.max_concurrency):
            await self.queue.put(SHUTDOWN)

    async def _worker_loop(self, worker_id: int) -> None:
        while True:
            item = await self.queue.get()
            try:
                if item is SHUTDOWN:
                    break
                await self._process(item, worker_id)
            except Exception:
                # Last-resort safety net. Pipelines that need to emit a
                # specific XFailedEvent on a specific exception type
                # should catch it inside their own _process() -- this
                # only catches something escaping that.
                logger.exception(
                    "%s worker %d failed processing %s",
                    type(self).__name__, worker_id, type(item).__name__,
                )
            finally:
                self.queue.task_done()

    async def _process(self, item, worker_id: int) -> None:
        raise NotImplementedError
