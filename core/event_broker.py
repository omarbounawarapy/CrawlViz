import asyncio
import logging
from typing import Any

from events import StopCrawlEvent

from .event_registry import EventRegistry

logger = logging.getLogger(__name__)


class EventBroker:
    """Central pub/sub bus. Pipelines never call each other directly --
    everything is emit() into the bus and put() out to subscribers.

    See report section 0.19 ("Decouplage producteur-consommateur") for
    why: this is what lets a slow pipeline stall without blocking the
    ones around it, and what makes replay possible.
    """

    def __init__(self):
        self.event_bus = asyncio.Queue()
        self.registry = EventRegistry()
        self.running = True
        self.active_tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        """Drain the event bus, fanning each event out to its subscribers.

        Runs until `running` is False and the bus has been fully drained,
        then waits for any in-flight dispatch tasks before returning.
        """
        while self.running or not self.event_bus.empty():
            event: Any = await self.event_bus.get()

            try:
                # StopCrawlEvent gets broker-level bookkeeping (flip
                # `running` off so emit() stops accepting new work) *and*
                # still needs to reach any pipeline subscribed to it
                # below, so subscribers with cleanup logic (flushing the
                # export buffer, closing the canonicalization writer,
                # telling the UI the crawl ended) actually run instead of
                # sitting on their queue forever.
                if isinstance(event, StopCrawlEvent):
                    await self._handle_stop(event)

                consumers = self.registry.event_consumers(event)
                for consumer in consumers:
                    task = asyncio.create_task(self._dispatch(consumer, event))
                    self.active_tasks.add(task)
                    task.add_done_callback(self.active_tasks.discard)

            finally:
                self.event_bus.task_done()

        await self._shutdown()

    async def _dispatch(self, consumer, event: Any) -> None:
        try:
            await consumer.put(event)
        except Exception:
            logger.exception("Consumer failed to handle %s", type(event).__name__)

    async def emit(self, event: Any) -> None:
        """Publish `event` to every subscriber registered for its type.

        Silently dropped once the broker has stopped accepting new work.
        """
        if not self.running:
            return  # drop events after stop
        await self.event_bus.put(event)

    def subscribe(self, pipeline, event_types) -> None:
        """Register `pipeline` to receive every event type in `event_types`."""
        self.registry.subscribe(pipeline, event_types)

    async def _handle_stop(self, event: StopCrawlEvent) -> None:
        logger.info(
            "Stop condition reached: reason=%s nodes=%d depth=%d duration=%.2fs",
            event.reason, event.node_count, event.max_depth, event.duration,
        )
        self.running = False  # stop accepting new events

    async def _shutdown(self) -> None:
        if self.active_tasks:
            await asyncio.gather(*self.active_tasks, return_exceptions=True)

        # Every registered pipeline gets told to stop here, not just the
        # ones individually subscribed to StopCrawlEvent for their own
        # cleanup logic. Before this, a pipeline sitting on an empty
        # queue when the crawl ended had no guaranteed way to notice and
        # exit its worker loop -- which meant Crawler.start()'s
        # asyncio.gather(*tasks) could hang indefinitely even after the
        # crawl had genuinely finished.
        for consumer in self.registry.all_consumers():
            stop = getattr(consumer, "stop", None)
            if stop is None:
                continue
            try:
                result = stop()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception(
                    "%s failed to stop cleanly", type(consumer).__name__
                )

        logger.info("Broker shutdown complete")
