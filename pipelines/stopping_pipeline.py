import asyncio
import time

from events import NodeAddedEvent, StopCrawlEvent, StorageNodeUpdatedEvent

from .base_pipeline import BasePipeline


class StoppingPipeline(BasePipeline):
    """Watches crawl progress against the blueprint's stop conditions and
    emits StopCrawlEvent the moment any one of them is met.

    Reads its thresholds directly off the Crawler instance so they stay
    in sync with whatever the blueprint configured.
    """

    def __init__(self, crawler, max_queue_size: int = 0, max_concurrency: int = 1):
        super().__init__(max_concurrency=max_concurrency)
        self.event_broker = crawler.event_broker

        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)

        # Conditions
        self.max_nodes = crawler.max_nodes
        self.max_depth = crawler.max_depth
        self.max_duration = crawler.max_duration
        self.no_progress_timeout = crawler.no_progress_timeout
        self.target_url = crawler.target_url

        # State
        self.node_count = 0
        self.max_seen_depth = 0

        self.start_time = time.time()
        self.last_activity_time = time.time()

        self.stopped = False
        self._stop_lock = asyncio.Lock()

        self.handlers = {
            NodeAddedEvent: self._on_node_added,
            StorageNodeUpdatedEvent: self._on_node_updated,
        }

    async def _process(self, event, worker_id: int) -> None:
        handler = self.handlers.get(type(event))
        if handler:
            await handler(event)

        await self._check_time_conditions()

    async def _on_node_added(self, event: NodeAddedEvent) -> None:
        node = event.node

        self.node_count += 1
        self.max_seen_depth = max(self.max_seen_depth, node.get_depth())
        self.last_activity_time = time.time()

        if self.node_count >= self.max_nodes:
            await self._stop("MAX_NODES_REACHED")

        if node.get_depth() >= self.max_depth:
            await self._stop("MAX_DEPTH_REACHED")

        if self.target_url and self.target_url in node.get_full_url():
            await self._stop("TARGET_REACHED", detail=node.get_full_url())

    async def _on_node_updated(self, event: StorageNodeUpdatedEvent) -> None:
        self.last_activity_time = time.time()

    async def _check_time_conditions(self) -> None:
        now = time.time()

        if now - self.start_time >= self.max_duration:
            await self._stop("TIME_LIMIT_REACHED")

        if now - self.last_activity_time >= self.no_progress_timeout:
            await self._stop("NO_PROGRESS")

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
