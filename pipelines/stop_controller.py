import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass

from crawlviz.events import (
    BasePipeline,
    NodeAddedEvent,
    PageFetchedEvent,
    StopCrawlEvent,
    StorageNodeUpdatedEvent,
)
from crawlviz.shared import BackgroundTasks

# How many checks in a row must find the crawl idle before the frontier counts as drained.
# One check can fall between an event leaving one stage and arriving at the next.
IDLE_CONFIRMATION_CHECKS = 3


@dataclass(frozen=True)
class StopConditions:
    max_nodes: int
    max_duration: float
    no_progress_timeout: float
    target_url: str = ""
    # Whether nothing is queued or in flight anywhere in the crawl (see StopController).
    frontier_idle: Callable[[], bool] | None = None


class StopController(BasePipeline):
    """Watches crawl progress against the blueprint's stop conditions and
    emits StopCrawlEvent the moment any one of them is met.

    Takes its thresholds as a ``StopConditions``; the Crawler builds one
    from the blueprint.

    ``max_nodes`` counts successfully fetched pages. ``max_depth`` is not a
    stop condition: StorageSink refuses to admit nodes deeper than it,
    and the crawl ends with ``FRONTIER_EXHAUSTED`` once the frontier drains.

    ``conditions.frontier_idle`` tells whether nothing is queued or in flight anywhere in the
    crawl. When it holds for ``IDLE_CONFIRMATION_CHECKS`` checks in a row no new page can
    appear, so the crawl stops at once instead of waiting for the no-progress timeout.
    Without it the controller never reports a drained frontier.
    """

    def __init__(
        self,
        event_broker,
        conditions: StopConditions,
        max_queue_size: int = 0,
        max_concurrency: int = 1,
        check_interval: float = 0.1,
    ):
        super().__init__(max_concurrency=max_concurrency)
        self.check_interval = check_interval
        self._frontier_idle = conditions.frontier_idle
        self._idle_checks = 0
        self.event_broker = event_broker

        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)

        # Conditions
        self.max_nodes = conditions.max_nodes
        self.max_duration = conditions.max_duration
        self.no_progress_timeout = conditions.no_progress_timeout
        self.target_url = conditions.target_url

        # State
        self.node_count = 0
        self.max_seen_depth = 0

        self.start_time = time.time()
        self.last_activity_time = time.time()

        self.stopped = False
        self._stop_lock = asyncio.Lock()

        self.handlers = {
            NodeAddedEvent: self._on_node_added,
            PageFetchedEvent: self._on_page_fetched,
            StorageNodeUpdatedEvent: self._on_node_updated,
        }

    @property
    def event_types(self) -> tuple[type, ...]:
        # StopCrawlEvent has no handler: it only runs the time check once more.
        return (*self.handlers, StopCrawlEvent)

    async def start(self) -> None:
        # Time conditions must fire on a quiet crawl too, not only when
        # an event arrives.
        timer = BackgroundTasks()
        timer.spawn(self._time_watch(), name="StoppingPipeline-time-watch")
        try:
            await super().start()
        finally:
            await timer.cancel_all()

    async def _time_watch(self) -> None:
        while not self.stopped:
            await asyncio.sleep(self.check_interval)
            await self._check_time_conditions()
            await self._check_frontier_drained()

    async def _check_frontier_drained(self) -> None:
        if self._frontier_idle is None or self.stopped:
            return
        # This controller's own queue counts: a page it has not counted yet may still
        # reach the page budget.
        idle = self._frontier_idle() and not self.has_pending_work
        self._idle_checks = self._idle_checks + 1 if idle else 0
        if self._idle_checks >= IDLE_CONFIRMATION_CHECKS:
            await self._stop("FRONTIER_EXHAUSTED")

    async def _process(self, event, worker_id: int) -> None:
        handler = self.handlers.get(type(event))
        if handler:
            await handler(event)

        await self._check_time_conditions()

    async def _on_node_added(self, event: NodeAddedEvent) -> None:
        node = event.node

        self.last_activity_time = time.time()

        if self.target_url and self.target_url in node.get_full_url():
            await self._stop("TARGET_REACHED", detail=node.get_full_url())

    async def _on_page_fetched(self, event: PageFetchedEvent) -> None:
        self.node_count += 1
        self.max_seen_depth = max(self.max_seen_depth, event.node.get_depth())
        self.last_activity_time = time.time()

        if self.node_count >= self.max_nodes:
            await self._stop("MAX_NODES_REACHED")

    async def _on_node_updated(self, event: StorageNodeUpdatedEvent) -> None:
        self.last_activity_time = time.time()

    async def _check_time_conditions(self) -> None:
        now = time.time()

        if now - self.start_time >= self.max_duration:
            await self._stop("TIME_LIMIT_REACHED")

        if now - self.last_activity_time >= self.no_progress_timeout:
            await self._stop("NO_PROGRESS")

    async def stop_on_request(self) -> None:
        """Stop the crawl because the user asked to (POST /stop)."""
        await self._stop("MANUAL_STOP")

    async def _stop(self, reason: str, detail: str | None = None) -> None:
        async with self._stop_lock:
            if self.stopped:
                return

            self.stopped = True

            duration = time.time() - self.start_time

            await self.event_broker.emit(
                StopCrawlEvent(
                    reason=reason,
                    node_count=self.node_count,
                    max_depth=self.max_seen_depth,
                    duration=duration,
                    detail=detail,
                )
            )
