import asyncio
import random
import time
from infrastructure import NetworkClient

from events import (
    NodeAddedEvent,
    PageFetchedEvent,
    RequestFailedEvent,

    RequestEnqueuedEvent,
    RequestStartedEvent,
    RequestResponseReceivedEvent,
)


class RequestsPipeline:
    def __init__(self, event_broker, max_concurrency=4, max_queue_size=0):
        self.event_broker = event_broker

        self.queue = asyncio.PriorityQueue(maxsize=max_queue_size)
        self.network_client = NetworkClient()

        self.max_concurrency = max_concurrency
        self.workers = []

        self.headers = {
            "User-Agent": "CoolBot/1.0 (https://example.com/contact; contact@example.com) BasedOnPythonRequests/2.31",
            "Accept-Encoding": "gzip, deflate",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        }

        self.handlers = {
            NodeAddedEvent: self.NODE_ADDED
        }

        self.min_delay = 1          # seconds between requests (tune this)
        self.last_request_time = 0.0
        self.backoff_delay = 0.0      # dynamic (for 429)
        self.max_backoff = 10.0

    # =====================================================
    # START
    # =====================================================
    async def start(self):
        self.workers = [
            asyncio.create_task(self.worker(i))
            for i in range(self.max_concurrency)
        ]
        await asyncio.gather(*self.workers)

    # =====================================================
    # ENTRY POINT
    # =====================================================
    async def put(self, event: NodeAddedEvent):
        await self.handlers[type(event)](event)

    # =====================================================
    # HANDLER (ingestion visibility)
    # =====================================================
    async def NODE_ADDED(self, event: NodeAddedEvent):
        await self.event_broker.emit(
            RequestEnqueuedEvent(
                correlation_id=event.node.get_id(),
                node_id=event.node.get_id(),
                queue_size=self.queue.qsize()
            )
        )

        await self.queue.put(event.node)

    # =====================================================
    # WORKER LOOP (FULL TRACE)
    # =====================================================
    async def worker(self, worker_id: int):
        while True:
            if not self.event_broker.running:
              break
            node = await self.queue.get()
            
            try:
            
                await self.event_broker.emit(
                    RequestStartedEvent(
                        worker_id=worker_id,
                        correlation_id=node.get_id(),
                        node_id=node.get_id(),
                        url=node.get_full_url()
                    )
                )

                # ============================
                # RATE LIMITING (GLOBAL PACE)
                # ============================
                now = time.monotonic()

                # enforce minimum delay between requests
                elapsed = now - self.last_request_time
                delay = max(self.min_delay - elapsed, 0)

                # include backoff if any
                delay += self.backoff_delay

                # add jitter (avoid sync bursts across workers)
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
                        correlation_id=node.get_id(),
                        node_id=node.get_id(),
                        response_size=len(response) if response else 0
                    )
                )
                # success → reduce backoff gradually
                self.backoff_delay = max(self.backoff_delay * 0.5, 0)

                await self.event_broker.emit(
                    PageFetchedEvent(
                        correlation_id=node.get_id(),
                        node=node,
                        content=response,
                    )
                )

            except Exception as e:
                error_str = str(e)

                # ============================
                # BACKOFF STRATEGY
                # ============================
                if "429" in error_str or "Too Many Requests" in error_str:
                    # exponential backoff
                    if self.backoff_delay == 0:
                        self.backoff_delay = 1.0
                    else:
                        self.backoff_delay = min(self.backoff_delay * 2, self.max_backoff)

                else:
                    # decay backoff if normal errors
                    self.backoff_delay = max(self.backoff_delay * 0.5, 0)

                await self.event_broker.emit(
                    RequestFailedEvent(
                        correlation_id=node.get_id(),
                        node=node,
                        error_type=type(e).__name__,
                        error_message=error_str,
                    )
                )

            finally:
                    self.queue.task_done()