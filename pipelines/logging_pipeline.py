import asyncio
import os
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

from .base_pipeline import BasePipeline


class LoggingPipeline(BasePipeline):
    """Renders each node-lifecycle event into one human-readable line,
    written to both the console and a per-crawl log file (see
    infrastructure.LogWriter). This is the crawl's narrative log --
    fine-grained trace events live in pipelines.debugging_pipeline instead.

    Lines are JSON objects. Concurrency is 1 on purpose: the file order is
    then the broker's dispatch order.
    """

    def __init__(self, event_broker, crawl_id, max_queue_size: int = 0, max_concurrency: int = 1,
                 log_root="logs"):
        super().__init__(max_concurrency=max_concurrency)
        self.event_broker = event_broker

        log_dir = os.path.join(log_root, crawl_id[:crawl_id.find("-")])
        os.makedirs(log_dir, exist_ok=True)

        path = os.path.join(log_dir, crawl_id)

        self.log_writer = LogWriter(path)

        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)

        # Maps each event type to the formatter method that renders its log line.
        self.state_map = {
            NodeAddedEvent: self._created,
            PageFetchedEvent: self._fetched,
            ContentFilteredEvent: self._filtered,
            TransformationCompletedEvent: self._transformed,
            StopCrawlEvent: self._stopped,
            LinksScoredEvent: self._scored,
            PriorityCalculatedEvent: self._expanded,
            ExportBatchCompletedEvent: self._exported,
            ScoreRescheduledEvent: self._rescheduled_score,
        }

    # =========================================================
    # START
    # =========================================================
    async def start(self) -> None:
        await self.log_writer.create_log_file()
        await super().start()
        await self.log_writer.close_file()

    # =========================================================
    # PROCESS ONE QUEUED EVENT
    # =========================================================
    async def _process(self, event, worker_id: int) -> None:
        try:
            handler = self.state_map.get(type(event))

            if handler:
                await self.log_writer.write_record(handler(event, worker_id))

        except Exception as e:
            await self.log_writer.write_record(
                {"event": "logging_error", "source": type(event).__name__, "error": str(e)}
            )

    # =========================================================
    # STATE FORMATTERS (CORE)
    # =========================================================

    def _created(self, e, w):
        node = e.node
        return {"event": "node_created", "node_id": node.get_id(),
                "url": unquote(node.get_link()), "depth": node.get_depth()}

    def _fetched(self, e, w):
        return {"event": "node_fetched", "node_id": e.node.get_id()}

    def _filtered(self, e, w):
        return {"event": "node_filtered", "node_id": e.node.get_id(),
                "links": len(e.links), "items": len(e.items)}

    def _transformed(self, e, w):
        return {"event": "node_transformed", "node_id": e.node.get_id(),
                "items": len(e.transformed_items)}

    def _scored(self, e, w):
        return {"event": "node_scored", "node_id": e.node.get_id(),
                "links": len(e.scored_links)}

    def _expanded(self, e, w):
        return {"event": "node_expanded", "node_id": e.parent.get_id(),
                "children": len(e.links)}

    def _exported(self, e, w):
        return {"event": "export_completed", "table": e.table,
                "inserted": e.inserted_count, "duration_ms": round(e.duration_ms, 2)}

    def _rescheduled_score(self, e, w):
        return {"event": "score_rescheduled", "node_id": e.node.get_id(),
                "new_priority": e.node.get_priority()}

    def _stopped(self, e, w):
        return {"event": "crawl_stopped", "reason": e.reason, "nodes": e.node_count,
                "depth": e.max_depth, "duration_s": round(e.duration, 2)}
