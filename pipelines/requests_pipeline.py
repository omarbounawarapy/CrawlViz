import asyncio
import random
import time

import aiohttp

from events import (
    NodeAddedEvent,
    PageFetchedEvent,
    RequestEnqueuedEvent,
    RequestFailedEvent,
    RequestResponseReceivedEvent,
    RequestStartedEvent,
)
from infrastructure import NetworkClient

from traceability.trace_context import bind_node

from .base_pipeline import SHUTDOWN
from .contracts import Fetcher
from .frontier_queue import FrontierQueue
from .robots import RobotsPolicy

ROBOTS_DISALLOWED = "RobotsDisallowed"


def is_rate_limited(error: Exception) -> bool:
    """True when the server answered 429 Too Many Requests."""
    return isinstance(error, aiohttp.ClientResponseError) and error.status == 429


class RequestsPipeline:
    """Fetches page content for every node, one HTTP request at a time
    per worker, with global rate limiting and 429 backoff shared across
    all workers.

    Deliberately not a BasePipeline subclass: unlike the event-dispatch
    pipelines, this one queues domain objects (Node), not events, and
    its worker loop is a rate-limited fetch loop with its own backoff
    state, not a generic handler dispatch. Forcing it onto the same
    shape would obscure more than it'd simplify. It still exposes a
    BasePipeline-compatible `stop()` (same SHUTDOWN sentinel) so
    EventBroker's shutdown broadcast reaches it the same way.
    """

    def __init__(
        self,
        event_broker,
        max_concurrency: int = 4,
        max_queue_size: int = 0,
        fetcher: Fetcher | None = None,
        min_delay: float = 1,
        user_agent: str = "CrawlViz/1.0",
        respect_robots: bool = False,
        rng: random.Random | None = None,
        jitter_max: float = 0.2,
        robots_ttl: float = 0.0,
        backoff_start: float = 1.0,
        max_backoff: float = 10.0,
        backoff_growth: float = 2.0,
        backoff_success_decay: float = 0.5,
        backoff_failure_decay: float = 0.5,
        extra_headers: dict[str, str] | None = None,
        accept: str = "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        accept_encoding: str = "gzip, deflate",
        accept_language: str = "",
    ):
        self.event_broker = event_broker
        self.rng = rng if rng is not None else random.Random()

        self.queue = FrontierQueue(maxsize=max_queue_size)
        self.network_client: Fetcher = fetcher if fetcher is not None else NetworkClient()

        self.max_concurrency = max_concurrency
        self.workers = []

        self.headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": accept_encoding,
            "Accept": accept,
        }
        if accept_language:
            self.headers["Accept-Language"] = accept_language
        self.headers.update(extra_headers or {})

        self.robots = (
            RobotsPolicy(self.network_client, user_agent, self.headers, robots_ttl)
            if respect_robots
            else None
        )

        self.handlers = {
            NodeAddedEvent: self._on_node_added,
        }

        self.min_delay = min_delay  # minimum seconds between requests
        self.last_request_time = 0.0
        self.backoff_delay = 0.0  # dynamic (grows on 429)
        self.max_backoff = max_backoff
        self.jitter_max = jitter_max
        self.backoff_start = backoff_start
        self.backoff_growth = backoff_growth
        self.backoff_success_decay = backoff_success_decay
        self.backoff_failure_decay = backoff_failure_decay

    # =========================================================
    # START
    # =========================================================
    async def start(self) -> None:
        self._pool_closed = False
        self._pool_next_id = 0
        self.workers = []
        self._pool_spawn(self.max_concurrency)
        while True:
            pending = [w for w in self.workers if not w.done()]
            if not pending:
                break
            await asyncio.gather(*pending)

    def _pool_spawn(self, count: int) -> None:
        for _ in range(count):
            self.workers.append(asyncio.create_task(self.worker(self._pool_next_id)))
            self._pool_next_id += 1

    def resize(self, workers: int) -> None:
        """Change the number of fetch workers of a running crawl (see
        BasePipeline.resize)."""
        if workers < 1:
            raise ValueError("workers must be at least 1")
        if getattr(self, "_pool_closed", False) or not hasattr(self, "_pool_next_id"):
            self.max_concurrency = workers
            return
        delta = workers - self.max_concurrency
        self.max_concurrency = workers
        if delta > 0:
            self._pool_spawn(delta)
        else:
            for _ in range(-delta):
                self._queue_shutdown()

    def _queue_shutdown(self) -> None:
        try:
            self.queue.put_nowait(SHUTDOWN)
        except asyncio.QueueFull:
            asyncio.ensure_future(self.queue.put(SHUTDOWN))

    # =========================================================
    # STOP
    # =========================================================
    async def stop(self) -> None:
        """Wake every worker so start() returns, even if the queue would
        otherwise sit empty forever (see BasePipeline for why this
        matters -- this pipeline predates it and isn't a subclass, but
        needs the same guarantee).
        """
        self._pool_closed = True
        for _ in range(self.max_concurrency):
            await self.queue.put(SHUTDOWN)

    @property
    def event_types(self) -> tuple[type, ...]:
        return tuple(self.handlers)

    # =========================================================
    # ENTRY POINT
    # =========================================================
    async def put(self, event: NodeAddedEvent) -> None:
        await self.handlers[type(event)](event)

    # =========================================================
    # HANDLER (INGESTION VISIBILITY)
    # =========================================================
    async def _on_node_added(self, event: NodeAddedEvent) -> None:
        await self.event_broker.emit(
            RequestEnqueuedEvent(
                correlation_id=str(event.node.get_id()),
                node_id=str(event.node.get_id()),
                queue_size=self.queue.qsize(),
            )
        )

        await self.queue.put(event.node)

    # =========================================================
    # WORKER LOOP (FULL TRACE)
    # =========================================================
    async def worker(self, worker_id: int) -> None:
        while True:
            node = await self.queue.get()

            try:
                if node is SHUTDOWN:
                    break
                bind_node(str(node.get_id()))

                await self.event_broker.emit(
                    RequestStartedEvent(
                        correlation_id=str(node.get_id()),
                        worker_id=worker_id,
                        node_id=str(node.get_id()),
                        url=node.get_full_url(),
                    )
                )

                if self.robots and not await self.robots.allowed(node.get_full_url()):
                    await self.event_broker.emit(
                        RequestFailedEvent(
                            correlation_id=str(node.get_id()),
                            node=node,
                            error_type=ROBOTS_DISALLOWED,
                            error_message="disallowed by robots.txt",
                        )
                    )
                    continue

                # Rate limiting (global pace): minimum inter-request delay,
                # plus any active backoff, plus jitter to avoid workers
                # bursting in sync.
                now = time.monotonic()
                elapsed = now - self.last_request_time
                delay = max(self.min_delay - elapsed, 0)
                delay += self.backoff_delay
                delay += self.rng.uniform(0, self.jitter_max)

                if delay > 0:
                    await asyncio.sleep(delay)

                self.last_request_time = time.monotonic()
                response = await self.network_client.emit_request(
                    {
                        "url": node.get_full_url(),
                        "headers": self.headers,
                        "data": "",
                        "method": "GET",
                    }
                )

                await self.event_broker.emit(
                    RequestResponseReceivedEvent(
                        correlation_id=str(node.get_id()),
                        node_id=str(node.get_id()),
                        response_size=len(response) if response else 0,
                    )
                )
                # Success: reduce backoff gradually.
                self.backoff_delay = max(self.backoff_delay * self.backoff_success_decay, 0)

                await self.event_broker.emit(
                    PageFetchedEvent(
                        correlation_id=str(node.get_id()),
                        node=node,
                        content=response,
                        node_id=str(node.get_id()),
                        parent_id=(str(node.parent.get_id()) if node.parent else None),
                        url=node.link.url if node.link else None,
                    )
                )

            except Exception as e:
                error_str = str(e) or type(e).__name__

                # Backoff strategy: exponential growth on rate-limit
                # responses, gradual decay otherwise.
                if is_rate_limited(e):
                    if self.backoff_delay == 0:
                        self.backoff_delay = self.backoff_start
                    else:
                        self.backoff_delay = min(
                            self.backoff_delay * self.backoff_growth, self.max_backoff
                        )
                else:
                    self.backoff_delay = max(self.backoff_delay * self.backoff_failure_decay, 0)

                await self.event_broker.emit(
                    RequestFailedEvent(
                        correlation_id=str(node.get_id()),
                        node=node,
                        error_type=type(e).__name__,
                        error_message=error_str,
                    )
                )

            finally:
                self.queue.task_done()
