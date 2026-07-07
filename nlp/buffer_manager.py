import asyncio
import logging

import numpy as np

logger = logging.getLogger(__name__)


class BufferManager:
    """Thread-safe buffer for pending vector additions to the semantic space.

    Vectors are added from scoring results (LLM expansions). The buffer is
    drained via drain() -- space mutation happens only there.

    Design constraints:
        - Adding to the buffer is non-blocking.
        - Flushing is explicit and controlled (not real-time).
        - The buffer never directly touches the VectorSpace.
    """

    def __init__(self, max_size: int = 500):
        self._buffer: list[tuple[str, np.ndarray, dict]] = []
        self._lock = asyncio.Lock()
        self.max_size = max_size
        self._total_added = 0
        self._total_flushed = 0

    # =========================================================
    # ADD
    # =========================================================

    async def add(self, key: str, vector: np.ndarray, metadata: dict | None = None) -> None:
        """Add a single vector to the buffer."""
        async with self._lock:
            if len(self._buffer) >= self.max_size:
                logger.warning("Buffer full (%d). Dropping: %s", self.max_size, key)
                return
            self._buffer.append((key, vector, metadata or {}))
            self._total_added += 1

    async def add_batch(self, items: list[tuple[str, np.ndarray, dict]]) -> None:
        """Add multiple vectors at once."""
        async with self._lock:
            available = self.max_size - len(self._buffer)
            to_add = items[:available]
            self._buffer.extend(to_add)
            self._total_added += len(to_add)
            if len(to_add) < len(items):
                dropped = len(items) - len(to_add)
                logger.warning("Buffer nearly full. Dropped %d vectors", dropped)

    # =========================================================
    # DRAIN
    # =========================================================

    async def drain(self) -> list[tuple[str, np.ndarray, dict]]:
        """Atomically drain and return the full buffer; the buffer is
        cleared as part of the same locked operation.
        """
        async with self._lock:
            items = list(self._buffer)
            self._buffer.clear()
            self._total_flushed += len(items)
            return items

    # =========================================================
    # INTROSPECTION
    # =========================================================

    async def size(self) -> int:
        async with self._lock:
            return len(self._buffer)

    def is_ready_for_flush(self, threshold: int = 50) -> bool:
        """Check without a lock -- approximate, safe for monitoring."""
        return len(self._buffer) >= threshold

    def stats(self) -> dict:
        return {
            "buffer_size": len(self._buffer),
            "total_added": self._total_added,
            "total_flushed": self._total_flushed,
            "pending": len(self._buffer),
        }
