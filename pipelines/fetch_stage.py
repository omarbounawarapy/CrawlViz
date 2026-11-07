import asyncio
import random

from config import USER_AGENT
from crawlviz.events import (
    SHUTDOWN,
    Fetcher,
    NodeAddedEvent,
    PageFetchedEvent,
    RequestEnqueuedEvent,
    RequestFailedEvent,
    RequestResponseReceivedEvent,
    RequestStartedEvent,
)
from crawlviz.shared import BackgroundTasks, NetworkClient, bind_node

from .frontier_queue import FrontierQueue
from .host_pacer import HostPacer, host_of
from .http_failure import BACKOFF_STATUSES, retry_after_seconds, status_of
from .robots import RobotsPolicy

ROBOTS_DISALLOWED = "RobotsDisallowed"
# Content types the extraction can parse; anything else is refused unread.
PAGE_CONTENT_TYPES = ("text/html", "application/xhtml+xml")


def is_rate_limited(error: Exception) -> bool:
    """True when the server answered 429 Too Many Requests or 503 Service Unavailable."""
    return status_of(error) in BACKOFF_STATUSES


class FetchStage:
    """Fetches page content for every node, one HTTP request at a time
    per worker, with per-host rate limiting and 429/503 backoff shared across
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
        user_agent: str = USER_AGENT,
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
        page_budget: int | None = None,
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

        # Pages the crawl may still fetch, counting those being fetched now; None is no limit.
        # The stop controller ends the crawl on the page that reaches max_nodes, but it hears
        # of that page only after the events queued ahead of it. A fetcher that answers at
        # once (an in-memory site) fetches ahead of that stop, so the budget is held here.
        self._pages_unclaimed = page_budget
        self._pages_in_flight = 0
        self._nodes_in_process = 0
        self._page_settled = asyncio.Condition()

        self.min_delay = min_delay  # minimum seconds between requests to one host
        self.pacer = HostPacer()
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
        self._background = BackgroundTasks()
        self._pool_spawn(self.max_concurrency)
        while True:
            pending = [w for w in self.workers if not w.done()]
            if not pending:
                break
            await asyncio.gather(*pending)
        await self._background.cancel_all()

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
            self._background.spawn(
                self.queue.put(SHUTDOWN), name="RequestsPipeline-shrink-shutdown"
            )

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
        async with self._page_settled:
            self._page_settled.notify_all()
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
        if self.budget_spent:
            # Nothing more will be fetched. Queueing the node could block this handler on a
            # full queue that no worker reads from, and the broker waits for its handlers
            # before it stops the stage.
            return
        await self.event_broker.emit(
            RequestEnqueuedEvent(
                correlation_id=str(event.node.get_id()),
                node_id=str(event.node.get_id()),
                queue_size=self.queue.qsize(),
            )
        )

        await self.queue.put(event.node)

    @property
    def has_pending_work(self) -> bool:
        """True while a node is queued or a worker holds one (fetching or waiting for a page)."""
        return self._nodes_in_process > 0 or not self.queue.empty()

    @property
    def pages_unclaimed(self) -> int | None:
        """Pages the crawl may still start fetching; None when there is no budget."""
        return self._pages_unclaimed

    @property
    def budget_spent(self) -> bool:
        """True once every page of the budget is fetched and none is being fetched, so no
        more fetches can happen: whatever still arrives is drained without a request."""
        return self._pages_unclaimed == 0 and self._pages_in_flight == 0

    async def _claim_page(self) -> bool:
        """Take one page of the budget before fetching it, waiting while the budget is
        all in use. False when the node must not be fetched: the crawl is stopping or the
        budget is spent."""
        async with self._page_settled:
            await self._page_settled.wait_for(self._can_claim_page)
            if self._pool_closed or self.budget_spent:
                return False
            if self._pages_unclaimed is not None:
                self._pages_unclaimed -= 1
                self._pages_in_flight += 1
            return True

    def _can_claim_page(self) -> bool:
        unclaimed = self._pages_unclaimed
        return self._pool_closed or unclaimed is None or unclaimed > 0 or self.budget_spent

    async def _settle_page(self, fetched: bool) -> None:
        """End a claim: the page stays counted when it was fetched and goes back to the
        budget when the fetch failed or was refused. Wakes every worker waiting for a
        page, since a failure frees one and the last success spends the budget."""
        if self._pages_unclaimed is None:
            return
        async with self._page_settled:
            self._pages_in_flight -= 1
            if not fetched:
                self._pages_unclaimed += 1
                self._page_settled.notify()
            if self.budget_spent:
                self._page_settled.notify_all()

    async def _wait_for_slot(self, url: str) -> None:
        """Rate limit, per host: the slot is claimed before sleeping, so
        concurrent workers queue behind each other instead of all seeing the
        same idle host. The spacing is the configured delay or the site's
        Crawl-delay, whichever is longer; backoff and jitter are added to this
        request's wait (jitter keeps workers from bursting in sync)."""
        crawl_delay = await self.robots.crawl_delay(url) if self.robots else None
        wait = self.pacer.reserve(
            host_of(url),
            spacing=max(self.min_delay, crawl_delay or 0.0),
            lead=self.backoff_delay + self.rng.uniform(0, self.jitter_max),
        )
        if wait > 0:
            await asyncio.sleep(wait)

    # =========================================================
    # WORKER LOOP (FULL TRACE)
    # =========================================================
    async def worker(self, worker_id: int) -> None:
        while True:
            node = await self.queue.get()
            self._nodes_in_process += 1
            holds_page = False
            page_fetched = False

            try:
                if node is SHUTDOWN:
                    break
                bind_node(str(node.get_id()))
                holds_page = await self._claim_page()
                if not holds_page:
                    continue

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

                await self._wait_for_slot(node.get_full_url())

                response = await self.network_client.emit_request(
                    {
                        "url": node.get_full_url(),
                        "headers": self.headers,
                        "data": "",
                        "method": "GET",
                        "content_types": PAGE_CONTENT_TYPES,
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
                page_fetched = True

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

                retry_after = retry_after_seconds(e)
                if retry_after is not None:
                    self.pacer.hold_off(host_of(node.get_full_url()), retry_after)

                await self.event_broker.emit(
                    RequestFailedEvent(
                        correlation_id=str(node.get_id()),
                        node=node,
                        error_type=type(e).__name__,
                        error_message=error_str,
                        status_code=status_of(e),
                    )
                )

            finally:
                if holds_page:
                    # Shielded so a cancelled worker still gives its claim back.
                    await asyncio.shield(self._settle_page(page_fetched))
                self._nodes_in_process -= 1
                self.queue.task_done()
