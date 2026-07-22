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

from .base_pipeline import BasePipeline


class ProcessingPipeline(BasePipeline):
    """Extracts links and structured items from each fetched page's HTML."""

    def __init__(
        self,
        event_broker,
        extraction_blueprint,
        max_concurrency: int = 1,
        max_queue_size: int = 0,
    ):
        super().__init__(max_concurrency=max_concurrency)
        self.event_broker = event_broker

        self.queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_queue_size)

        self.handlers = {
            PageFetchedEvent: self._on_page_fetched,
        }
        self.link_extractor = LinkExtractor()
        self.item_extractor = ItemExtractor(extraction_blueprint)

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
    # PROCESS ONE QUEUED (node, content) PAIR
    # =========================================================
    async def _process(self, item, worker_id: int) -> None:
        node, content = item

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
