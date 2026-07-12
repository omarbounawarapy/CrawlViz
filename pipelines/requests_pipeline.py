import asyncio
import random
import time

from events import (
    NodeAddedEvent,
    PageFetchedEvent,
    RequestEnqueuedEvent,
    RequestFailedEvent,
    RequestResponseReceivedEvent,
    RequestStartedEvent,
)
from infrastructure import NetworkClient


class RequestsPipeline:
    """Fetches page content for every node, one HTTP request at a time
    per worker, with global rate limiting and 429 backoff shared across
    all workers.
    """

    def __init__(self, event_broker, max_concurrency: int = 4, max_queue_size: int = 0):
        self.event_broker = event_broker

        self.queue = asyncio.PriorityQueue(maxsize=max_queue_size)
        self.network_client = NetworkClient()

        self.max_concurrency = max_concurrency
        self.workers = []

        self.headers = {
            "User-Agent": (
                "CoolBot/1.0 (https://example.com/contact; contact@example.com) "
                "BasedOnPythonRequests/2.31"
            ),
            "Accept-Encoding": "gzip, deflate",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        }

        self.handlers = {
            NodeAddedEvent: self._on_node_added,
        }

        self.min_delay = 1            # minimum seconds between requests
        self.last_request_time = 0.0
        self.backoff_delay = 0.0      # dynamic (grows on 429)
        self.max_backoff = 10.0

    # =========================================================
    # START
    # =========================================================
    async def start(self) -> None:
        self.workers = [
            asyncio.create_task(self.worker(i))
            for i in range(self.max_concurrency)
        ]
        await asyncio.gather(*self.workers)

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
            if not self.event_broker.running:
                break
            node = await self.queue.get()

            try:
                await self.event_broker.emit(
                    RequestStartedEvent(
                        correlation_id=str(node.get_id()),
                        worker_id=worker_id,
                        node_id=str(node.get_id()),
                        url=node.get_full_url(),
                    )
                )

                # Rate limiting (global pace): minimum inter-request delay,
                # plus any active backoff, plus jitter to avoid workers
                # bursting in sync.
                now = time.monotonic()
                elapsed = now - self.last_request_time
                delay = max(self.min_delay - elapsed, 0)
                delay += self.backoff_delay
                delay += random.uniform(0, 0.2)

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
                self.backoff_delay = max(self.backoff_delay * 0.5, 0)

                await self.event_broker.emit(
                    PageFetchedEvent(
                        correlation_id=str(node.get_id()),
                        node=node,
                        content=response,
                    )
                )

            except Exception as e:
                error_str = str(e)

                # Backoff strategy: exponential growth on rate-limit
                # responses, gradual decay otherwise.
                if "429" in error_str or "Too Many Requests" in error_str:
                    if self.backoff_delay == 0:
                        self.backoff_delay = 1.0
                    else:
                        self.backoff_delay = min(self.backoff_delay * 2, self.max_backoff)
                else:
                    self.backoff_delay = max(self.backoff_delay * 0.5, 0)

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
