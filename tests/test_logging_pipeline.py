import asyncio
import json

from events import StopCrawlEvent
from pipelines.logging_pipeline import LoggingPipeline


def test_lines_are_json_in_event_order(tmp_path):
    lp = LoggingPipeline(None, "t-2026", log_root=str(tmp_path))
    assert lp.max_concurrency == 1

    async def go():
        await lp.log_writer.create_log_file()
        for n in (1, 2):
            e = StopCrawlEvent.__new__(StopCrawlEvent)
            e.__dict__.update(reason="r", node_count=n, max_depth=1, duration=1.234)
            await lp._process(e, 0)
        await lp.log_writer.close_file()

    asyncio.run(go())
    rows = [json.loads(x) for x in (tmp_path / "t" / "t-2026").read_text().splitlines()]
    assert [r["nodes"] for r in rows] == [1, 2]
    assert rows[0]["event"] == "crawl_stopped" and "ts" in rows[0]
