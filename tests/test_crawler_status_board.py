"""The crawl owns a status board, streams it to the UI and lets a caller opt out."""

import asyncio
import json
from pathlib import Path

from core import Crawler
from crawlviz.events import NullStatusReporter
from crawlviz.telemetry import StatusBoard
from tests.synthetic_crawl import build_synthetic_crawl

SMALL_BUDGET = 20
CRAWL_TIMEOUT_SECONDS = 60.0
POLL_SECONDS = 0.005


def test_a_crawler_builds_a_status_board_by_default() -> None:
    crawler = Crawler("wikiMD.json")

    assert isinstance(crawler.status_board, StatusBoard)
    assert crawler.status_reporter is crawler.status_board


def test_a_given_board_is_the_crawlers_board() -> None:
    board = StatusBoard()

    assert Crawler("wikiMD.json", status_reporter=board).status_board is board


def test_the_null_reporter_leaves_the_crawler_without_a_board() -> None:
    crawler = Crawler("wikiMD.json", status_reporter=NullStatusReporter())

    assert crawler.status_board is None


async def test_a_change_on_the_board_reaches_the_ui_event_log(tmp_path: Path) -> None:
    crawl = build_synthetic_crawl(tmp_path, SMALL_BUDGET)
    crawler = crawl.crawler
    run = asyncio.create_task(crawler.start())
    while not hasattr(crawler, "_pipelines"):  # the watch starts with the stages
        await asyncio.sleep(POLL_SECONDS)

    assert crawler.status_board is not None
    crawler.status_board.report("fetch", "waiting", "backing_off")
    await asyncio.wait_for(run, CRAWL_TIMEOUT_SECONDS)

    log = crawler.paths.export_dir / crawler.crawl_id / "events.jsonl"
    messages = [json.loads(line) for line in log.read_text().splitlines()]
    sent = [message["entry"] for message in messages if message["type"] == "SUBSYSTEM_STATUS"]
    assert any(
        entry["subsystem"] == "fetch"
        and entry["state"] == "waiting"
        and entry["reason"] == "backing_off"
        for entry in sent
    )
