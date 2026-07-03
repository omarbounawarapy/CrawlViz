import asyncio
from utils import hash_item
from events import (
    ContentExtractedEvent,
    ContentFilteredEvent,
    FilteringEnqueuedEvent,
    FilteringInputSnapshotEvent,
    FilteringPipelineErrorEvent,
    FilteringWorkerCycleStartedEvent
)


class FilteringPipeline:
    def __init__(self, event_broker, storage, max_concurrency=10, max_queue_size=0):
        self.event_broker = event_broker
        self.storage = storage

        self.queue = asyncio.Queue(maxsize=max_queue_size)
        self.max_concurrency = max_concurrency
        self.workers = []

    # =====================================================
    # ENTRY POINT
    # =====================================================
    async def put(self, event: ContentExtractedEvent):
        await self.event_broker.emit(
            FilteringEnqueuedEvent(
                correlation_id=event.correlation_id,
                node_id=event.node.get_id(),
                queue_size=self.queue.qsize()
            )
        )
        await self.queue.put(event)

    # =====================================================
    # WORKER LOOP
    # =====================================================
    async def worker(self, worker_id: int):
        while self.event_broker.running:

            event = await self.queue.get()

            try:
                node = event.node

                await self.event_broker.emit(
                    FilteringWorkerCycleStartedEvent(
                        worker_id=worker_id,
                        correlation_id=event.correlation_id,
                        node_id=node.get_id()
                    )
                )

                # -----------------------------
                # SNAPSHOT
                # -----------------------------
                await self.event_broker.emit(
                    FilteringInputSnapshotEvent(
                        correlation_id=node.get_id(),
                        raw_links_count=len(event.links),
                        raw_items_count=len(event.items),
                    )
                )

                # -----------------------------
                # LINK FILTERING
                # -----------------------------
                links_result = self._filter_links(event.links, node)

                # -----------------------------
                # ITEM FILTERING
                # -----------------------------
                
                items_result = self._filter_items(event.items, node)
                # -----------------------------
                # OUTPUT
                # -----------------------------
                await self.event_broker.emit(
                    ContentFilteredEvent(
                        correlation_id=node.get_id(),
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

            finally:
                self.queue.task_done()

    # =====================================================
    # LINK FILTERING
    # =====================================================
    def _filter_links(self, links, node):
        accepted = []
        rejected_count = 0

        for link in links:
            if self.storage.link_seen(link.url):
                rejected_count += 1
                continue

            accepted.append(link)

        return {
            "accepted": accepted,
            "rejected_count": rejected_count
        }

    # =====================================================
    # ITEM FILTERING
    # =====================================================
    def _filter_items(self, items, node):
        accepted = []
        rejected_count = 0
        for item in items:
            
        

            # supports both:
            # - raw dict (old)
            # - (item, hash) tuple (new pipeline)
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
            "rejected_count": rejected_count
        }

    # =====================================================
    # START
    # =====================================================
    async def start(self):
        self.workers = [
            asyncio.create_task(self.worker(i))
            for i in range(self.max_concurrency)
        ]
        await asyncio.gather(*self.workers)