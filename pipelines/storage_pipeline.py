import asyncio

from events import (
    NodeAddedEvent,
    NodeContentSetEvent,
    PageFetchedEvent,
    PriorityCalculatedEvent,
    StorageItemStoredEvent,
    StorageLinkStoredEvent,
    StorageNodeAddedEvent,
    StorageNodeCreatedEvent,
    StorageNodeUpdatedEvent,
    StorageOperationFailedEvent,
    TransformationCompletedEvent,
)
from models import Node


class StoragePipeline:
    """Persists the crawl graph: creates child nodes from calculated
    priorities, and writes transformed items/links/content back onto
    their node once each stage completes.
    """

    def __init__(self, storage, event_broker, max_queue_size: int = 0, max_concurrency: int = 1):
        self.event_broker = event_broker
        self.storage = storage

        self.queue = asyncio.Queue(maxsize=max_queue_size)
        self.max_concurrency = max_concurrency
        self.workers = []

        self.handlers = {
            PageFetchedEvent: self._on_page_fetched,
            PriorityCalculatedEvent: self._on_priority_calculated,
            TransformationCompletedEvent: self._on_transformation_completed,
        }

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
    # ENTRY POINT
    # =========================================================
    async def put(self, event) -> None:
        # Enqueue rather than dispatching inline, so `worker()` actually
        # serializes handler calls through `max_concurrency` -- storage
        # mutations like `Storage.next_id()` / `add_node()` rely on that
        # serialization to stay consistent (see models/storage.py).
        await self.queue.put(event)

    # =========================================================
    # WORKER LOOP
    # =========================================================
    async def worker(self, worker_id: int) -> None:
        while self.event_broker.running:
            event = await self.queue.get()

            try:
                handler = self.handlers.get(type(event))
                if handler:
                    await handler(event)

            except Exception as e:
                await self.event_broker.emit(
                    StorageOperationFailedEvent(
                        correlation_id=getattr(event, "correlation_id", None),
                        stage="WORKER",
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )
                )

            finally:
                self.queue.task_done()

    # =========================================================
    # PRIORITY -> NODE CREATION
    # =========================================================
    async def _on_priority_calculated(self, event: PriorityCalculatedEvent) -> None:
        """Create and persist one child Node per prioritized link.

        `event.links` entries are ``{"link": Link, "score": int, "priority": float}``
        dicts, as produced by PriorityPipeline._compute_priorities.
        """
        parent = event.parent

        for entry in event.links:
            link = entry["link"]
            llm_score = entry["score"]
            priority = entry["priority"]

            node_id = self.storage.next_id()

            node = Node(
                node_id,
                link=link,
                llm_score=llm_score,
                priority=priority,
                parent=parent,
            )

            await self.event_broker.emit(
                StorageNodeCreatedEvent(
                    correlation_id=str(node_id),
                    node_id=str(node_id),
                    parent_id=str(parent.get_id()),
                    url=node.get_full_url(),
                    llm_score=llm_score,
                    priority=priority,
                )
            )

            self.storage.add_node(node)

            await self.event_broker.emit(
                StorageNodeAddedEvent(
                    correlation_id=str(node_id),
                    node=node,
                )
            )

            await self.event_broker.emit(
                NodeAddedEvent(
                    correlation_id=str(node_id),
                    node=node,
                )
            )

    # =========================================================
    # TRANSFORMATION -> STORAGE PERSISTENCE
    # =========================================================
    async def _on_transformation_completed(self, event: TransformationCompletedEvent) -> None:
        node = event.node

        # Store items (final shape)
        for item, hash_value in event.transformed_items:
            self.storage.add_item(item, hash_value, node)

            await self.event_broker.emit(
                StorageItemStoredEvent(
                    correlation_id=str(node.get_id()),
                    node_id=str(node.get_id()),
                    item_hash=hash_value,
                )
            )

        # Store links
        self.storage.add_links(event.links)

        await self.event_broker.emit(
            StorageLinkStoredEvent(
                correlation_id=str(node.get_id()),
                node_id=str(node.get_id()),
                links_count=len(event.links),
            )
        )

        # Node update
        node.set_links(event.links)
        node.update_state()

        await self.event_broker.emit(
            StorageNodeUpdatedEvent(
                correlation_id=str(node.get_id()),
                node=node,
                links=event.links,
                items=event.transformed_items,
            )
        )

    async def _on_page_fetched(self, event: PageFetchedEvent) -> None:
        node = event.node
        content = event.content
        node.set_content(content)
        await self.event_broker.emit(
            NodeContentSetEvent(
                correlation_id=str(node.get_id()),
                node=node,
                content=content,
            )
        )
