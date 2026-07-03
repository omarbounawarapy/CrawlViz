import asyncio
import logging

from .buffer_manager import BufferManager

logger = logging.getLogger(__name__)


class SpaceUpdater:
    """
    Periodic background task that:
    1. Drains the BufferManager
    2. Commits buffered vectors to NLPService (which writes to VectorSpace)
    3. Saves the updated space to disk

    NEVER called in the hot scoring path.

    Flushing is purely interval-driven: every `flush_interval` seconds,
    whatever is in the buffer gets committed. `flush_threshold` is not
    currently used to trigger an *earlier* flush -- doing that would
    need the buffer to wake this loop on insert rather than relying on
    a fixed sleep, which is a bigger change than this pass makes.

    Space remains stable between flushes — this is intentional.
    """

    def __init__(
        self,
        nlp_service,
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

    # =========================================================
    # LIFECYCLE
    # =========================================================

    async def start(self) -> None:
        """Main loop — runs until stopped."""
        self._running = True
        logger.info(
            "SpaceUpdater started (interval=%ss, threshold=%d)",
            self.flush_interval, self.flush_threshold,
        )

        while self._running:
            await asyncio.sleep(self.flush_interval)
            await self._maybe_flush()

    def stop(self) -> None:
        self._running = False
        logger.info("SpaceUpdater stopped")

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
        """Explicitly trigger a flush — e.g., on crawl end."""
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