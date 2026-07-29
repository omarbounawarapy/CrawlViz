import asyncio
import logging
from typing import TYPE_CHECKING

from events import StopCrawlEvent

from .buffer_manager import BufferManager

if TYPE_CHECKING:
    from services import NLPService

logger = logging.getLogger(__name__)


class SpaceUpdater:
    """Periodic background task that:

    1. Drains the BufferManager.
    2. Commits buffered vectors to NLPService (which writes to VectorSpace).
    3. Saves the updated space to disk.

    NEVER called in the hot scoring path.

    Flushing is interval-driven: every `flush_interval` seconds, whatever
    is in the buffer gets committed. `flush_threshold` is not currently
    used to trigger an *earlier* flush -- doing that would need the
    buffer to wake this loop on insert rather than relying on a fixed
    wait, which is a bigger change than this pass makes.

    Shutdown: this loop waits on an ``asyncio.Event`` (with the interval
    as a timeout) rather than a plain ``asyncio.sleep``, so ``stop()``
    wakes it immediately instead of waiting out the rest of the current
    interval. Subscribing this object to ``StopCrawlEvent`` on the
    ``EventBroker`` (it implements ``put()`` for exactly this) is what
    actually triggers that -- previously nothing ever called ``stop()``,
    so this task ran forever and ``Crawler.start()``'s
    ``asyncio.gather(...)`` never returned even after a crawl reached its
    own stop conditions.

    Space remains stable between flushes -- this is intentional.
    """

    def __init__(
        self,
        nlp_service: "NLPService",
        buffer_manager: BufferManager,
        flush_interval: float = 60.0,
        flush_threshold: int = 50,
    ):
        self.nlp_service = nlp_service
        self.buffer = buffer_manager
        self.flush_interval = flush_interval
        self.flush_threshold = flush_threshold
        self._running = False
        self._flush_count = 0
        self._stop_event = asyncio.Event()

        # Lets this be subscribed directly to the EventBroker like a
        # pipeline, so it reacts to StopCrawlEvent the same way anything
        # else does, rather than needing bespoke wiring in core.Crawler.
        self.handlers = {
            StopCrawlEvent: self._on_stop_crawl,
        }

    # =========================================================
    # LIFECYCLE
    # =========================================================

    async def start(self) -> None:
        """Main loop -- runs until stop() is called (directly, or via a
        subscribed StopCrawlEvent).
        """
        self._running = True
        logger.info(
            "SpaceUpdater started (interval=%ss, threshold=%d)",
            self.flush_interval, self.flush_threshold,
        )

        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.flush_interval
                )
            except asyncio.TimeoutError:
                pass  # normal case: interval elapsed, no stop requested

            if self._stop_event.is_set():
                break

            await self._maybe_flush()

        # Don't drop whatever's still buffered when the crawl ends.
        await self.force_flush()
        self._running = False
        logger.info("SpaceUpdater stopped")

    def stop(self) -> None:
        """Request an immediate, graceful stop.

        Safe to call multiple times or before start() has run.
        """
        self._stop_event.set()

    async def put(self, event) -> None:
        """EventBroker entry point -- lets this be subscribed directly
        to StopCrawlEvent instead of needing a bespoke shutdown path.
        """
        handler = self.handlers.get(type(event))
        if handler:
            await handler(event)

    async def _on_stop_crawl(self, event: StopCrawlEvent) -> None:
        self.stop()

    # =========================================================
    # FLUSH LOGIC
    # =========================================================

    async def _maybe_flush(self) -> None:
        """Flush the buffer if it has anything in it."""
        size = await self.buffer.size()
        if size == 0:
            return

        await self._flush()

    async def _flush(self) -> None:
        items = await self.buffer.drain()
        if not items:
            return

        # inject into nlp_service buffer and flush to space
        for key, vec, meta in items:
            self.nlp_service.space.add_vector(key, vec, meta)

        self.nlp_service.space.version += 1
        self.nlp_service.save_space()
        self._flush_count += 1

        logger.info(
            "Flush #%d: %d vectors committed (space size now %d)",
            self._flush_count, len(items), self.nlp_service.space_size(),
        )

    async def force_flush(self) -> None:
        """Explicitly trigger a flush -- e.g., on crawl end."""
        logger.info("Force flush triggered")
        await self._flush()

    # =========================================================
    # STATS
    # =========================================================

    def stats(self) -> dict:
        return {
            "flush_count": self._flush_count,
            "buffer_stats": self.buffer.stats(),
            "space_size": self.nlp_service.space_size(),
        }
