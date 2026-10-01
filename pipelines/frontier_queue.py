import asyncio
import heapq
import itertools


class FrontierQueue(asyncio.PriorityQueue):
    """Queue that pops the highest-priority Node first.

    asyncio.PriorityQueue is a min-heap, so ordering by `Node.priority`
    directly would pop the lowest priority first. Items are stored as
    `(key, seq, item)`: `key` is `-node.priority` (read when the node is
    enqueued, so `decrease_priority` before a requeue takes effect),
    `seq` keeps FIFO order among equal priorities and means items are
    never compared to each other. Anything without a `priority` (the
    shutdown sentinel) sorts first so it wakes a worker immediately.
    """

    def _init(self, maxsize):
        self._queue = []
        self._seq = itertools.count()

    def _put(self, item):
        priority = getattr(item, "priority", None)
        key = float("-inf") if priority is None else -priority
        heapq.heappush(self._queue, (key, next(self._seq), item))

    def _get(self):
        return heapq.heappop(self._queue)[2]
