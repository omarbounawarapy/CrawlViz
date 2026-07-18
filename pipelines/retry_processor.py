import asyncio
import logging

from events import (
    EmptyScoreResultsEvent,
    RequestFailedEvent,
    RetryOperationFailedEvent,
    ScoreRescheduledEvent,
)

logger = logging.getLogger(__name__)


class RetryProcessor:
    """Reacts to soft scoring failures and page-fetch failures by
    demoting and rescheduling the affected node, rather than dropping it
    from the crawl outright.

    Args:
        storage: Shared crawl Storage.
        event_broker: The crawl's EventBroker.
        requests_pipeline: The live RequestsPipeline instance. Required for
            RequestFailedEvent handling to actually retry -- without it,
            failures are logged but the node is not requeued.
        max_request_retries: How many times a single node may be requeued
            after a page-fetch failure before it's given up on.
    """

    def __init__(
        self,
        storage,
        event_broker,
        requests_pipeline=None,
        max_queue_size: int = 0,
        max_concurrency: int = 1,
        max_request_retries: int = 3,
    ):
        self.event_broker = event_broker
        self.storage = storage
        self.requests_pipeline = requests_pipeline
        self.max_request_retries = max_request_retries
        # Per-node retry attempt counter, keyed by node id.
        self._retry_counts: dict[int, int] = {}

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
        """Requeue a node whose page fetch failed, up to `max_request_retries`.

        Requeues directly onto RequestsPipeline's own queue (bypassing the
        broker) rather than re-emitting NodeAddedEvent, since NodeAddedEvent
        also fans out to ScoringPipeline/StoppingPipeline/etc., which would
        incorrectly treat a network retry as a brand-new node.
        """
        node = event.node
        node_id = node.get_id()
        attempts = self._retry_counts.get(node_id, 0) + 1
        self._retry_counts[node_id] = attempts

        if attempts > self.max_request_retries:
            logger.warning(
                "Node %s exceeded max retries (%d) after %s: %s -- giving up",
                node_id, self.max_request_retries, event.error_type, event.error_message,
            )
            return

        if self.requests_pipeline is None:
            logger.warning(
                "RequestFailedEvent for node %s but RetryProcessor has no "
                "requests_pipeline wired in -- cannot retry (%s: %s)",
                node_id, event.error_type, event.error_message,
            )
            return

        node.decrease_priority(2)
        logger.info(
            "Retrying node %s (attempt %d/%d) after %s: %s",
            node_id, attempts, self.max_request_retries,
            event.error_type, event.error_message,
        )
        await self.requests_pipeline.queue.put(node)
