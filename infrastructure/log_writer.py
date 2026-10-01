import json
import logging
from datetime import datetime, timezone

from .async_file_handler import AsyncFileHandler


class LogWriter(AsyncFileHandler):
    """Session log writer: every line goes to both the console and the
    per-session log file on disk (report section 0.18.3/0.27.9 -- the
    real-time terminal trace plus a persisted, browsable log per run).
    """

    async def create_log_file(self) -> None:
        await super().create_file()

    async def write_log(self, log: str) -> None:
        print(log)  # console sink
        await super().write_line(log + "\n")  # file sink

    async def write_record(self, record: dict) -> None:
        """One JSON object per line, UTC timestamp first, to the file and
        the ``crawlviz.crawl`` stdlib logger (console)."""
        stamped = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **record}
        line = json.dumps(stamped, default=str)
        logging.getLogger("crawlviz.crawl").info(line)
        await super().write_line(line)
