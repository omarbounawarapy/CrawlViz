import asyncio

from events import (
    ContentExtractedEvent,
    ContentFilteredEvent,
    FilteringEnqueuedEvent,
    FilteringInputSnapshotEvent,
    FilteringPipelineErrorEvent,
    FilteringWorkerCycleStartedEvent,
)
from utils import hash_item

from .base_pipeline import BasePipeline


class FilteringPipeline(BasePipeline):
    """Drops links and items already seen elsewhere in the crawl.

    Deduplication is storage-backed (Storage.link_seen / item_seen), so
    it holds across the whole crawl graph, not just within one node.
    """

    def __init__(self, event_broker, storage, max_concurrency: int = 10, max_queue_size: int = 0):
        super().__init__(max_concurrency=max_concurrency)
        self.event_broker = event_broker
        self.storage = storage

        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)

    # =========================================================
    # ENTRY POINT
    # =========================================================
    async def put(self, event: ContentExtractedEvent) -> None:
        await self.event_broker.emit(
            FilteringEnqueuedEvent(
                correlation_id=event.correlation_id,
                node_id=str(event.node.get_id()),
                queue_size=self.queue.qsize(),
            )
        )
        await self.queue.put(event)

    # =========================================================
    # PROCESS ONE QUEUED EVENT
    # =========================================================
    async def _process(self, event: ContentExtractedEvent, worker_id: int) -> None:
        try:
            node = event.node

            await self.event_broker.emit(
                FilteringWorkerCycleStartedEvent(
                    correlation_id=event.correlation_id,
                    worker_id=worker_id,
                    node_id=str(node.get_id()),
                )
            )

            # Snapshot
            await self.event_broker.emit(
                FilteringInputSnapshotEvent(
                    correlation_id=str(node.get_id()),
                    raw_links_count=len(event.links),
                    raw_items_count=len(event.items),
                )
            )

            # Link filtering
            links_result = self._filter_links(event.links, node)

            # Item filtering
            items_result = self._filter_items(event.items, node)

            # Output
            await self.event_broker.emit(
                ContentFilteredEvent(
                    correlation_id=str(node.get_id()),
                    node=node,
                    links=links_result["accepted"],
                    items=items_result["accepted"],
                    rejected_links_count=links_result["rejected_count"],
                    rejected_items_count=items_result["rejected_count"],
                    accepted_links_count=len(links_result["accepted"]),
                    accepted_items_count=len(items_result["accepted"]),
                )
            )

        except Exception as e:
            await self.event_broker.emit(
                FilteringPipelineErrorEvent(
                    correlation_id=getattr(event, "correlation_id", None),
                    node=getattr(event, "node", None),
                    stage="WORKER_EXECUTION",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
            )

    # =========================================================
    # LINK FILTERING
    # =========================================================
    def _filter_links(self, links, node) -> dict:
        accepted = []
        rejected_count = 0

        for link in links:
            if self.storage.link_seen(link.url):
                rejected_count += 1
                continue

            accepted.append(link)

        return {
            "accepted": accepted,
            "rejected_count": rejected_count,
        }

    # =========================================================
    # ITEM FILTERING
    # =========================================================
    def _filter_items(self, items, node) -> dict:
        accepted = []
        rejected_count = 0
        for item in items:
            # Items arrive either as a plain dict, or as an (item, hash)
            # tuple when the extractor has already computed the hash.
            if isinstance(item, tuple):
                raw_item, item_hash = item
            else:
                raw_item = item
                item_hash = hash_item(raw_item)

            if self.storage.item_seen(item_hash):
                rejected_count += 1
                continue

            accepted.append((raw_item, item_hash))
        return {
            "accepted": accepted,
            "rejected_count": rejected_count,
        }
