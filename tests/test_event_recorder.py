import asyncio
import json

from config.paths import RuntimePaths
from core.crawler import Crawler
from tests.test_event_wiring import FAKE_BLUEPRINT
from ui_bridge.event_recorder import EventRecorder, RecordingGateway


class _Gateway:
    def __init__(self):
        self.sent = []
        self.stopped = False

    async def broadcast(self, message):
        self.sent.append(message)

    async def stop(self):
        self.stopped = True


def test_recording_gateway_writes_each_message_in_order_and_forwards(tmp_path):
    inner = _Gateway()
    rec = EventRecorder(tmp_path / "run")
    gw = RecordingGateway(inner, rec)

    async def go():
        await gw.broadcast({"type": "NODE_ADDED", "n": 1})
        await gw.broadcast({"type": "CRAWL_STOPPED", "n": 2})
        await gw.stop()

    asyncio.run(go())
    lines = [json.loads(x) for x in (tmp_path / "run" / "events.jsonl").read_text().splitlines()]
    assert [m["n"] for m in lines] == [1, 2]
    assert inner.sent == lines and inner.stopped


def test_crawler_ui_layer_records_snapshot_and_manifest(tmp_path):
    crawler = Crawler("wikiMD.json", paths=RuntimePaths.under(tmp_path), seed=7)
    crawler._load_blueprint_config(FAKE_BLUEPRINT)
    crawler._build_ui_layer({})
    run_dir = tmp_path / "export" / crawler.crawl_id
    first = json.loads((run_dir / "events.jsonl").read_text().splitlines()[0])
    assert first["type"] == "SNAPSHOT_FULL"
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["seed"] == 7
    assert manifest["blueprint"]["blueprint_id"] == "test-bp"
    assert manifest["embedding_model"] and "runtime_config" in manifest
