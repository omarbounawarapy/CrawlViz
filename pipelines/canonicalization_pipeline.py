import asyncio
import json
import logging
import os
from datetime import datetime

from events import PageFetchedEvent, StopCrawlEvent
from infrastructure.async_file_handler import AsyncFileHandler

logger = logging.getLogger(__name__)


class CanonicalizationPipeline:
    """Writes every fetched page's raw content to a session-scoped
    documents.jsonl file, independent of the extraction/transform/export
    path -- a durable, schema-agnostic record of everything the crawler
    saw, regardless of what the blueprint chose to extract.
    """

    def __init__(self, crawl_id, event_broker, export_path):
        self.event_broker = event_broker
        self.export_path = export_path
        self.crawl_id = crawl_id

        self.queue = asyncio.Queue()

        # Runtime control
        self.running = False
        self._task = None

        # File setup
        self.dir_path = os.path.join(export_path, crawl_id)
        os.makedirs(self.dir_path, exist_ok=True)

        self.file_path = os.path.join(self.dir_path, "documents.jsonl")
        self.writer = AsyncFileHandler(self.file_path)

        # Event routing
        self.handlers = {
            PageFetchedEvent: self._on_page_fetched,
            StopCrawlEvent: self._on_stop_crawl,
        }

    # =========================================================
    # ENTRY
    # =========================================================
    async def put(self, event) -> None:
        await self.queue.put(event)

    # =========================================================
    # START PIPELINE
    # =========================================================
    async def start(self) -> None:
        self.running = True

        await self.writer.create_file()

        self._task = asyncio.create_task(self._run())

        await self._task

    # =========================================================
    # MAIN LOOP (SINGLE CONSUMER)
    # =========================================================
    async def _run(self) -> None:
        while True:
            event = await self.queue.get()

            try:
                if event is None:
                    break

                handler = self.handlers.get(type(event))
                if handler:
                    await handler(event)

            except Exception:
                logger.exception("Failed to process event in canonicalization pipeline")

            finally:
                self.queue.task_done()

        await self.writer.close_file()

    # =========================================================
    # EVENT HANDLERS
    # =========================================================

    async def _on_page_fetched(self, event: PageFetchedEvent) -> None:
        node = event.node
        content = event.content

        doc_id = node.get_id()
        url = node.get_full_url()
        now = datetime.now()

        doc = {
            "id": doc_id,
            "source_type": "web",
            "source_uri": url,
            "title": "",
            "text": content,
            "language": "en",
            "retrieved_at": now.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "metadata": {
                "crawler": "crawlviz",
            },
        }

        # JSONL write (ensure string)
        await self.writer.write_line(json.dumps(doc, ensure_ascii=False))

    async def _on_stop_crawl(self, event: StopCrawlEvent) -> None:
        self.running = False

        # Graceful shutdown signal (poison pill).
        await self.queue.put(None)
