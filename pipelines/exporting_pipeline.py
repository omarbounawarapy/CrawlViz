import asyncio
import json
import logging
import sqlite3
import time
from datetime import UTC, datetime

from config import ITEMS_DB_PATH
from events import ExportBatchCompletedEvent, StopCrawlEvent, TransformationCompletedEvent
from models import Node

from .base_pipeline import SHUTDOWN

logger = logging.getLogger(__name__)


class ExportingPipeline:
    """Writes transformed items to SQLite, one table per (domain, blueprint).

    Rows are idempotent: INSERT OR REPLACE keyed on the item's content
    hash (report section 0.23.2 / 0.26.6), so re-running the same
    transform on the same content is a no-op rather than a duplicate.
    """

    def __init__(
        self,
        crawl_id,
        blueprint_id,
        blueprint,
        event_broker,
        db_path=ITEMS_DB_PATH,
        batch_size=50,
    ):
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

        self.running = True  # internal lifecycle flag

        self.handlers = {
            TransformationCompletedEvent: self._on_transformation_completed,
            StopCrawlEvent: self._on_stop_crawl,
        }

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
        await self.queue.put(SHUTDOWN)

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

        # Final flush once the loop exits, so nothing buffered is lost.
        self._finalize()

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
    def _flush_with_events(self, table: str) -> None:
        """Batch flush that also emits ExportBatchCompletedEvent for observability."""
        if not self._buffer:
            return

        start = time.time()

        try:
            self.cursor.execute("BEGIN")
            for t, node, item, extraction_blueprint, item_hash in self._buffer:
                self._insert_row(t, node, item, extraction_blueprint, item_hash)
            self.conn.commit()

            duration = (time.time() - start) * 1000
            asyncio.create_task(
                self.event_broker.emit(
                    ExportBatchCompletedEvent(
                        correlation_id="export",
                        table=table,
                        inserted_count=len(self._buffer),
                        duration_ms=duration,
                    )
                )
            )

        except Exception:
            self.conn.rollback()
            logger.exception("Batch flush failed for table %s", table)

        finally:
            self._buffer.clear()

    def _flush(self) -> None:
        """Simple flush with no event emission -- used at shutdown."""
        if not self._buffer:
            return

        try:
            self.cursor.execute("BEGIN")
            for table, node, item, extraction_blueprint, item_hash in self._buffer:
                self._insert_row(table, node, item, extraction_blueprint, item_hash)
            self.conn.commit()

        except Exception:
            self.conn.rollback()
            logger.exception("Final flush failed")

        finally:
            self._buffer.clear()

    # =========================================================
    # SCHEMA / ROW HELPERS
    # =========================================================
    def _get_table_name(self, node: Node) -> str:
        domain = node.get_domain_base_url().replace("https://", "").replace(".", "_")
        return f"{domain}_{self.blueprint_id}"

    def _ensure_table(self, table_name: str, extraction_blueprint: dict) -> None:
        if table_name in self._initialized_tables:
            return
        fields = extraction_blueprint.get("fields", {})
        columns = ["id TEXT PRIMARY KEY", "crawl_id TEXT", "url TEXT", "created_at TEXT"]
        for field_name, spec in fields.items():
            store_type = spec.get("export_type", "text")
            sql_type = self._map_type(store_type)
            columns.append(f"{field_name} {sql_type}")
        sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns)})"
        self.cursor.execute(sql)
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

    def _map_type(self, t: str) -> str:
        return {
            "real": "REAL",
            "int": "INTEGER",
            "json": "TEXT",
            "text": "TEXT",
        }.get(t, "TEXT")

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
