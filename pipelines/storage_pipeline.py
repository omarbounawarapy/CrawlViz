import asyncio

from models import Node
from events import (
    PriorityCalculatedEvent,
    TransformationCompletedEvent,
    NodeAddedEvent,
    StorageNodeCreatedEvent,
    StorageNodeAddedEvent,
    StorageNodeUpdatedEvent,
    StorageItemStoredEvent,
    StorageLinkStoredEvent,
    StorageOperationFailedEvent,
    PageFetchedEvent,
    NodeContentSetEvent
)


class StoragePipeline:
    def __init__(self, storage, event_broker, max_queue_size=0, max_concurrency=1):
        self.event_broker = event_broker
        self.storage = storage

        self.queue = asyncio.Queue(maxsize=max_queue_size)
        self.max_concurrency = max_concurrency
        self.workers = []

        self.handlers = {
            PageFetchedEvent : self.PAGE_FETCHED,
            PriorityCalculatedEvent: self.PRIORITY_CALCULATED,
            TransformationCompletedEvent: self.TRANSFORMATION_COMPLETED,
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

    # =====================================================
    # ENTRY POINT
    # =====================================================
    async def put(self, event):
        handler = self.handlers.get(type(event))
        if handler:
            await handler(event)

    # =====================================================
    # WORKER LOOP
    # =====================================================
    async def worker(self, worker_id):
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

    # =====================================================
    # PRIORITY → NODE CREATION
    # =====================================================
    async def PRIORITY_CALCULATED(self, event: PriorityCalculatedEvent):
        parent = event.parent
        """
        link = { 
          link : link object 
          score : llm_score int 
          priority : final calculated priority float
        
        }
        

        """

        for entry in event.links:
            link = entry["link"]
            
            llm_score = entry["score"]
            priority = entry["priority"]

            node_id = self.storage.next_id()

            node = Node(
                node_id,
                link = link,
                llm_score=llm_score,
                priority=priority,
                parent=parent
            )

            await self.event_broker.emit(
                StorageNodeCreatedEvent(
                    correlation_id=str(node_id),
                    node_id=node_id,
                    parent_id=parent.get_id(),
                    url=node.get_full_url(),
                    llm_score=llm_score,
                    priority=priority,
                )
            )

            self.storage.add_node(node)

            await self.event_broker.emit(
                StorageNodeAddedEvent(
                    correlation_id=str(node_id),
                    node=node
                )
            )

            await self.event_broker.emit(
                NodeAddedEvent(
                    correlation_id=str(node_id),
                    node=node
                )
            )

    # =====================================================
    # TRANSFORMATION → STORAGE PERSISTENCE
    # =====================================================
    async def TRANSFORMATION_COMPLETED(self, event: TransformationCompletedEvent):
        node = event.node

        # -----------------------------
        # STORE ITEMS (FINAL SHAPE)
        # -----------------------------
        for item, hash_value in event.transformed_items:
            self.storage.add_item(item, hash_value, node)

            await self.event_broker.emit(
                StorageItemStoredEvent(
                    correlation_id=node.get_id(),
                    node_id=node.get_id(),
                    item_hash=hash_value
                )
            )

        # -----------------------------
        # STORE LINKS
        # -----------------------------
        self.storage.add_links(event.links)

        await self.event_broker.emit(
            StorageLinkStoredEvent(
                correlation_id=node.get_id(),
                node_id=node.get_id(),
                links_count=len(event.links)
            )
        )

        # -----------------------------
        # NODE UPDATE
        # -----------------------------
        node.set_links(event.links)
        node.update_state()

        await self.event_broker.emit(
            StorageNodeUpdatedEvent(
                correlation_id=node.get_id(),
                node=node,
                links=event.links,
                items=event.transformed_items,
            )
        )


    async def PAGE_FETCHED(self,e : PageFetchedEvent):
        node = e.node 
        content = e.content
        node.set_content(content)
        await self.event_broker.emit(
            NodeContentSetEvent(
                correlation_id = str(node.get_id()),
                node = node ,
                content = content
            )
        )