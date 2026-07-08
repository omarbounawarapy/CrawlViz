import asyncio

from events import (
    ContentExtractedEvent,
    ExtractionInputSnapshotEvent,
    ExtractionStartedEvent,
    ItemExtractionCompletedEvent,
    LinkExtractionCompletedEvent,
    PageFetchedEvent,
    ProcessingExtractionFailedEvent,
)
from models import ItemExtractor, LinkExtractor


class ProcessingPipeline:
    """Extracts links and structured items from each fetched page's HTML."""

    def __init__(
        self,
        event_broker,
        extraction_blueprint,
        max_concurrency: int = 1,
        max_queue_size: int = 0,
    ):
        self.event_broker = event_broker

        self.queue = asyncio.PriorityQueue(maxsize=max_queue_size)

        self.max_concurrency = max_concurrency
        self.workers = []

        self.handlers = {
            PageFetchedEvent: self._on_page_fetched,
        }
        self.link_extractor = LinkExtractor()
        self.item_extractor = ItemExtractor(extraction_blueprint)

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
    # ENTRY
    # =========================================================
    async def put(self, event: PageFetchedEvent) -> None:
        await self.handlers[type(event)](event)

    # =========================================================
    # HANDLER
    # =========================================================
    async def _on_page_fetched(self, event: PageFetchedEvent) -> None:
        await self.event_broker.emit(
            ExtractionInputSnapshotEvent(
                correlation_id=str(event.node.get_id()),
                node_id=str(event.node.get_id()),
                content_size=len(event.content) if event.content else 0,
            )
        )

        await self.queue.put((event.node, event.content))

    # =========================================================
    # WORKER
    # =========================================================
    async def worker(self, worker_id: int) -> None:
        while self.event_broker.running:
            node, content = await self.queue.get()

            try:
                await self.event_broker.emit(
                    ExtractionStartedEvent(
                        correlation_id=str(node.get_id()),
                        worker_id=worker_id,
                        node_id=str(node.get_id()),
                        content_size=len(content) if content else 0,
                    )
                )

                # Link extraction
                links = self.link_extractor.extract_links(content, node)
                await self.event_broker.emit(
                    LinkExtractionCompletedEvent(
                        correlation_id=str(node.get_id()),
                        node_id=str(node.get_id()),
                        extracted_links_count=len(links),
                    )
                )

                # Item extraction
                items = self.item_extractor.extract_items(content, node)
                await self.event_broker.emit(
                    ItemExtractionCompletedEvent(
                        correlation_id=str(node.get_id()),
                        node_id=str(node.get_id()),
                        extracted_items_count=len(items),
                    )
                )

                # Final output
                await self.event_broker.emit(
                    ContentExtractedEvent(
                        correlation_id=str(node.get_id()),
                        node=node,
                        links=links,
                        items=items,
                    )
                )

            except Exception as e:
                await self.event_broker.emit(
                    ProcessingExtractionFailedEvent(
                        correlation_id=str(node.get_id()),
                        node=node,
                        stage="EXTRACTION",
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )
                )

            finally:
                self.queue.task_done()
