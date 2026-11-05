import asyncio
import json
import logging
import sqlite3
import time
from datetime import UTC, datetime

from config import ITEMS_DB_PATH
from crawlviz.events import ExportBatchCompletedEvent, StopCrawlEvent, TransformationCompletedEvent
from crawlviz.shared import BackgroundTasks
from models import Node

from .base_pipeline import SHUTDOWN
from .export_tables import ensure_table

logger = logging.getLogger(__name__)


class ExportSink:
    """Writes transformed items to SQLite, one table per (domain, blueprint).

    Rows are idempotent within a crawl: INSERT OR REPLACE keyed on
    (crawl_id, content hash) (report section 0.23.2 / 0.26.6), so re-running
    the same transform on the same content is a no-op rather than a duplicate,
    while a later crawl keeps its own rows instead of overwriting this one's.
    """

    def __init__(
        self,
        crawl_id,
        blueprint_id,
        blueprint,
        event_broker,
        db_path=ITEMS_DB_PATH,
        batch_size: int = 50,
    ) -> None:
        self.event_broker = event_broker
        self.db_path = db_path
        self.batch_size = batch_size
        self.crawl_id = crawl_id
        self.blueprint_id = blueprint_id
        self.queue = asyncio.Queue()
        self.extraction_blueprint = blueprint.get("extraction", {})

        self.conn = None
        self.cursor = None

        self._initialized_tables = set()
        self._buffer = []
        self._background = BackgroundTasks()

        self.running = True  # internal lifecycle flag

        self.handlers = {
            TransformationCompletedEvent: self._on_transformation_completed,
            StopCrawlEvent: self._on_stop_crawl,
        }

    @property
    def event_types(self) -> tuple[type, ...]:
        return tuple(self.handlers)

    # =========================================================
    # INIT
    # =========================================================
    def _init_db(self) -> None:
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.cursor = self.conn.cursor()

    # =========================================================
    # ENTRY
    # =========================================================
    async def put(self, event) -> None:
        handler = self.handlers.get(type(event))
        if handler:
            await handler(event)

    async def _on_transformation_completed(self, event: TransformationCompletedEvent) -> None:
        await self.queue.put(event)

    async def _on_stop_crawl(self, event: StopCrawlEvent) -> None:
        await self.stop()

    async def stop(self) -> None:
        """Signal shutdown and wake the worker immediately.

        Setting `self.running = False` alone isn't enough: the `while`
        loop only re-checks it *after* `queue.get()` returns, so a
        worker blocked on an empty queue (the normal state once the
        crawl has stopped and no more TransformationCompletedEvents are
        coming) would otherwise never wake up to notice.
        """
        self.running = False
        self.queue.put_nowait(SHUTDOWN)  # the queue is unbounded, so there is always room

    # =========================================================
    # START
    # =========================================================
    async def start(self) -> None:
        self._init_db()
        await self.worker()

    # =========================================================
    # WORKER LOOP
    # =========================================================
    async def worker(self) -> None:
        # The final flush lives in `finally` so it also runs when the task is
        # cancelled (POST /stop). Otherwise rows still in the buffer are lost.
        try:
            while self.running or not self.queue.empty():
                event = await self.queue.get()

                try:
                    if event is SHUTDOWN:
                        break

                    node = event.node
                    extraction_blueprint = self.extraction_blueprint
                    table = self._get_table_name(node)

                    self._ensure_table(table, extraction_blueprint)

                    for item, item_hash in event.transformed_items:
                        normalized_item = self._normalize_item(item, extraction_blueprint)
                        self._buffer.append(
                            (table, node, normalized_item, extraction_blueprint, item_hash)
                        )

                    if len(self._buffer) >= self.batch_size:
                        self._flush_with_events(table)
                        self.conn.commit()

                except Exception:
                    logger.exception("Failed to process export batch")

                finally:
                    self.queue.task_done()
        finally:
            try:
                self._finalize()
            finally:
                await self._background.cancel_all()

    def _finalize(self) -> None:
        try:
            self._flush()
            if self.conn:
                self.conn.commit()
        finally:
            if self.conn:
                self.conn.close()
                logger.info("Export connection closed (crawl_id=%s)", self.crawl_id)

    # =========================================================
    # FLUSH
    # =========================================================
    def _write_buffer(self) -> int:
        """Insert every buffered row in one transaction and return how many.

        The buffer is cleared only after the commit. On failure the transaction
        is rolled back, the rows stay buffered for the next flush, and the
        error is raised.
        """
        try:
            self.cursor.execute("BEGIN")
            for table, node, item, extraction_blueprint, item_hash in self._buffer:
                self._insert_row(table, node, item, extraction_blueprint, item_hash)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        inserted = len(self._buffer)
        self._buffer.clear()
        return inserted

    def _flush_with_events(self, table: str) -> None:
        """Batch flush that also emits ExportBatchCompletedEvent for observability."""
        if not self._buffer:
            return

        start = time.time()

        try:
            inserted = self._write_buffer()
        except Exception:
            logger.exception(
                "Batch flush failed for table %s; keeping %d rows for the next flush",
                table,
                len(self._buffer),
            )
            return

        duration = (time.time() - start) * 1000
        self._background.spawn(
            self.event_broker.emit(
                ExportBatchCompletedEvent(
                    correlation_id="export",
                    table=table,
                    inserted_count=inserted,
                    duration_ms=duration,
                )
            ),
            name="export-batch-completed",
        )

    def _flush(self) -> None:
        """Flush with no event emission, used at shutdown.

        Rows that cannot be written now have no later flush to wait for, so the
        failure is logged with the number of rows lost and raised.
        """
        if not self._buffer:
            return

        try:
            self._write_buffer()
        except Exception:
            logger.exception(
                "Final flush failed; %d buffered rows were not saved", len(self._buffer)
            )
            raise

    # =========================================================
    # SCHEMA / ROW HELPERS
    # =========================================================
    def _get_table_name(self, node: Node) -> str:
        domain = node.get_domain_base_url().replace("https://", "").replace(".", "_")
        return f"{domain}_{self.blueprint_id}"

    def _ensure_table(self, table_name: str, extraction_blueprint: dict) -> None:
        if table_name in self._initialized_tables:
            return
        ensure_table(self.cursor, table_name, extraction_blueprint)
        self._initialized_tables.add(table_name)

    def _cast(self, value, t: str, field: str):
        if value is None:
            return None

        try:
            if t == "real":
                return float(value)
            if t == "int":
                return int(value)
            if t == "json":
                return json.dumps(value, ensure_ascii=False)
            if isinstance(value, (list, dict)):
                return json.dumps(value, ensure_ascii=False)
            return str(value)

        except Exception:
            logger.warning("Failed to cast field=%s value=%r as %s", field, value, t)
            return None

    def _insert_row(
        self, table: str, node: Node, item: dict, extraction_blueprint: dict, item_hash: str
    ) -> None:
        fields = extraction_blueprint.get("fields", {})
        utc_now = datetime.now(UTC)
        row = {
            "id": item_hash,
            "crawl_id": self.crawl_id,
            "url": node.get_full_url(),
            "created_at": utc_now.isoformat(),
        }

        for field, value in item.items():
            if field not in fields:
                continue
            store_type = fields[field].get("export_type", "text")
            row[field] = self._cast(value, store_type, field)

        cols = ", ".join(row.keys())
        vals = list(row.values())
        placeholders = ", ".join(["?"] * len(vals))

        sql = f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})"
        self.cursor.execute(sql, vals)

    def _normalize_item(self, item: dict, extraction_blueprint: dict) -> dict:
        fields = extraction_blueprint.get("fields", {})
        normalized = {}

        for k, v in item.items():
            if k not in fields:
                continue

            t = fields[k].get("export_type", "text")
            if t == "json" and isinstance(v, str):
                # Best-effort: if it's already a JSON string, parse it so
                # it round-trips as structured data rather than double-encoded text.
                try:
                    v = json.loads(v)
                except json.JSONDecodeError:
                    pass

            normalized[k] = v

        return normalized
