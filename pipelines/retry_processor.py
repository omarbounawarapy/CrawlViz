import asyncio

from events import (
    EmptyScoreResultsEvent,
    RequestFailedEvent,
    RetryOperationFailedEvent,
    ScoreRescheduledEvent,
)


class RetryProcessor:
    """Reacts to soft scoring failures by demoting and rescheduling the
    affected node, rather than dropping it from the crawl outright.
    """

    def __init__(self, storage, event_broker, max_queue_size: int = 0, max_concurrency: int = 1):
        self.event_broker = event_broker
        self.storage = storage

        self.queue = asyncio.Queue(maxsize=max_queue_size)
        self.max_concurrency = max_concurrency
        self.workers = []

        self.handlers = {
            RequestFailedEvent: self._on_request_failed,
            EmptyScoreResultsEvent: self._on_empty_score_results,
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
        handler = self.handlers.get(type(event))
        if handler:
            await handler(event)

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
                    RetryOperationFailedEvent(
                        correlation_id=getattr(event, "correlation_id", None),
                        stage="WORKER",
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )
                )

            finally:
                self.queue.task_done()

    async def _on_empty_score_results(self, event: EmptyScoreResultsEvent) -> None:
        """Demote and reschedule a node whose links came back with no scores."""
        node = event.node
        node.decrease_priority(5)

        await self.event_broker.emit(
            ScoreRescheduledEvent(
                correlation_id=str(node.get_id()),
                node=node,
            )
        )

    async def _on_request_failed(self, event: RequestFailedEvent) -> None:
        # Request failures are already captured for observability via
        # RequestFailedEvent (see pipelines.debugging_pipeline); no active
        # retry is triggered here yet.
        pass
