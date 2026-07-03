import asyncio

from events import (
    RequestFailedEvent,
    EmptyScoreResults,
    ScoreRescheduledEvent,
    RetryOperationFailedEvent
    
)


class RetryProcessor:
    def __init__(self, storage, event_broker, max_queue_size=0, max_concurrency=1):
        self.event_broker = event_broker
        self.storage = storage

        self.queue = asyncio.Queue(maxsize=max_queue_size)
        self.max_concurrency = max_concurrency
        self.workers = []

        self.handlers = {
           RequestFailedEvent: self.REQUEST_FAILED,
            EmptyScoreResults: self.EMPTY_SCORE
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
                    RetryOperationFailedEvent(
                        correlation_id=getattr(event, "correlation_id", None),
                        stage="WORKER",
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )
                )

            finally:
                self.queue.task_done()

    async def EMPTY_SCORE(self,event : EmptyScoreResults):
        node = event.node
        node.decrease_priority(5)

        await self.event_broker.emit(
            ScoreRescheduledEvent(
                correlation_id=node.get_id(),
                node=node,
            )
        )

    async def REQUEST_FAILED(self,event : RequestFailedEvent):
        pass
    