import asyncio
import os
from datetime import datetime
from urllib.parse import unquote

from events import (
    ContentFilteredEvent,
    ExportBatchCompletedEvent,
    LinksScoredEvent,
    NodeAddedEvent,
    PageFetchedEvent,
    PriorityCalculatedEvent,
    ScoreRescheduledEvent,
    StopCrawlEvent,
    TransformationCompletedEvent,
)
from infrastructure import LogWriter


class LoggingPipeline:
    """Renders each node-lifecycle event into one human-readable line,
    written to both the console and a per-crawl log file (see
    infrastructure.LogWriter). This is the crawl's narrative log --
    fine-grained trace events live in pipelines.debugging_pipeline instead.
    """

    def __init__(self, event_broker, crawl_id, max_queue_size: int = 0, max_concurrency: int = 5):
        self.event_broker = event_broker

        log_dir = os.path.join("logs", crawl_id[:crawl_id.find("-")])
        os.makedirs(log_dir, exist_ok=True)

        path = os.path.join(log_dir, crawl_id)

        self.log_writer = LogWriter(path)

        self.queue = asyncio.Queue(maxsize=max_queue_size)
        self.max_concurrency = max_concurrency
        self.workers = []

        # Maps each event type to the formatter method that renders its log line.
        self.state_map = {
            NodeAddedEvent: self._created,
            PageFetchedEvent: self._fetched,
            ContentFilteredEvent: self._filtered,
            TransformationCompletedEvent: self._transformed,
            StopCrawlEvent: self._on_stop_crawl,
            LinksScoredEvent: self._scored,
            PriorityCalculatedEvent: self._expanded,
            ExportBatchCompletedEvent: self._exported,
            ScoreRescheduledEvent: self._rescheduled_score,
        }

    # =========================================================
    # ENTRY
    # =========================================================
    async def put(self, event) -> None:
        await self.queue.put(event)

    # =========================================================
    # START
    # =========================================================
    async def start(self) -> None:
        await self.log_writer.create_log_file()

        self.workers = [
            asyncio.create_task(self.worker(i))
            for i in range(self.max_concurrency)
        ]

    # =========================================================
    # STOP
    # =========================================================
    async def _on_stop_crawl(self) -> None:
        # 1. Wait until all queued events have been processed.
        await self.queue.join()

        # 2. Send each worker a shutdown signal (poison pill).
        for _ in range(self.max_concurrency):
            await self.queue.put(None)

        # 3. Wait for every worker to exit.
        await asyncio.gather(*self.workers)

        await self.log_writer.close_file()

    # =========================================================
    # WORKER
    # =========================================================
    async def worker(self, worker_id: int) -> None:
        while True:
            event = await self.queue.get()

            if event is None:
                self.queue.task_done()
                break

            try:
                handler = self.state_map.get(type(event))

                if handler:
                    log_line = handler(event, worker_id)
                    await self.log_writer.write_log(log_line)

            except Exception as e:
                await self.log_writer.write_log(
                    f"[LOGGING_ERROR] event={type(event).__name__} error={str(e)}"
                )

            finally:
                self.queue.task_done()

    # =========================================================
    # STATE FORMATTERS (CORE)
    # =========================================================

    def _prefix(self, worker_id: int) -> str:
        now = datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M:%S") + f".{int(now.microsecond / 1000):03d}"
        return f"[{time_str}][W{worker_id}]"

    def _created(self, e, w):
        node = e.node
        url = unquote(node.get_link())

        return (
            f"{self._prefix(w)} "
            f"[NODE] id={node.get_id()} → CREATED "
            f"url={url} depth={node.get_depth()}"
        )

    def _fetched(self, e, w):
        node = e.node
        return (
            f"{self._prefix(w)} "
            f"[NODE] id={node.get_id()} → FETCHED"
        )

    def _filtered(self, e, w):
        node = e.node
        return (
            f"{self._prefix(w)} "
            f"[NODE] id={node.get_id()} → FILTERED "
            f"(links={len(e.links)}, items={len(e.items)})"
        )

    def _transformed(self, e, w):
        node = e.node
        return (
            f"{self._prefix(w)} "
            f"[NODE] id={node.get_id()} → TRANSFORMED "
            f"(items={len(e.transformed_items)})"
        )

    def _scored(self, e, w):
        node = e.node
        return (
            f"{self._prefix(w)} "
            f"[NODE] id={node.get_id()} → SCORED "
            f"(links={len(e.scored_links)})"
        )

    def _expanded(self, e, w):
        parent = e.parent
        return (
            f"{self._prefix(w)} "
            f"[NODE] id={parent.get_id()} → EXPANDED "
            f"(children={len(e.links)})"
        )

    def _exported(self, e, w):
        return (
            f"{self._prefix(w)} [EXPORT] COMPLETED "
            f"table={e.table} "
            f"inserted={e.inserted_count} "
            f"duration_ms={round(e.duration_ms, 2)}"
        )

    def _rescheduled_score(self, e, w):
        return (
            f"{self._prefix(w)} [SCORE_RESCHEDULE] "
            f"[NODE] id={e.node.get_id()} "
            f"new_priority={e.node.get_priority()}"
        )
