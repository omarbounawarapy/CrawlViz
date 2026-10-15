from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from config.runtime_config import default_runtime_config
from core.live_settings import (LIVE_BINDINGS, LiveSettingsError, apply_live,
                                live_fields)


def test_every_live_field_has_a_binding():
    assert live_fields() == set(LIVE_BINDINGS)


def _pipes():
    return {"requests": SimpleNamespace(min_delay=1, jitter_max=0.2, max_backoff=10),
            "retry": SimpleNamespace(max_request_retries=3, max_scoring_retries=3)}


def test_apply_sets_pipeline_attributes():
    pipes = _pipes()
    cfg = apply_live(default_runtime_config(), pipes,
                     {"fetch": {"min_delay": 0.25, "backoff_max": 20},
                      "retries": {"max_request_retries": 7}})
    assert pipes["requests"].min_delay == 0.25
    assert pipes["requests"].max_backoff == 20
    assert pipes["retry"].max_request_retries == 7
    assert cfg.fetch.min_delay == 0.25


def test_rejects_non_live_and_invalid_without_side_effects():
    pipes = _pipes()
    with pytest.raises(LiveSettingsError):
        apply_live(default_runtime_config(), pipes, {"fetch": {"user_agent": "x", "min_delay": 5}})
    with pytest.raises(ValidationError):
        apply_live(default_runtime_config(), pipes, {"fetch": {"min_delay": -1}})
    assert pipes["requests"].min_delay == 1


def test_patch_live_route_without_crawl_is_409(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from routes import run as run_routes

    monkeypatch.setattr(run_routes, "_current_crawler", None)
    r = TestClient(app).patch("/config/live", json={"values": {"fetch": {"min_delay": 0.5}}})
    assert r.status_code == 409


def test_patch_live_route_applies_to_running_crawler(monkeypatch):
    from fastapi.testclient import TestClient
    from core import Crawler
    from main import app
    from routes import run as run_routes

    crawler = Crawler("x.json")
    crawler._pipelines = _pipes()
    monkeypatch.setattr(run_routes, "_current_crawler", crawler)
    c = TestClient(app)
    r = c.patch("/config/live", json={"values": {"fetch": {"min_delay": 0.5}}})
    assert r.status_code == 200 and crawler._pipelines["requests"].min_delay == 0.5
    r = c.patch("/config/live", json={"values": {"fetch": {"user_agent": "x"}}})
    assert r.status_code == 422


def test_resize_grows_and_shrinks_a_running_pipeline():
    import asyncio
    from pipelines.base_pipeline import BasePipeline

    class P(BasePipeline):
        def __init__(self):
            super().__init__(max_concurrency=2)
            self.queue = asyncio.Queue()
            self.seen = set()

        async def _process(self, item, worker_id):
            self.seen.add(worker_id)
            await asyncio.sleep(0.05)

    async def run():
        p = P()
        task = asyncio.create_task(p.start())
        await asyncio.sleep(0.01)
        p.resize(5)
        assert p.max_concurrency == 5
        for i in range(10):
            await p.queue.put(i)
        await p.queue.join()
        grown = len([w for w in p.workers if not w.done()])
        p.resize(1)
        await asyncio.sleep(0.2)
        shrunk = len([w for w in p.workers if not w.done()])
        await p.stop()
        await asyncio.wait_for(task, 2)
        return grown, shrunk, len(p.seen)

    grown, shrunk, seen = asyncio.run(run())
    assert (grown, shrunk) == (5, 1) and seen == 5


def test_worker_fields_are_live_via_resize():
    pipes = {"requests": SimpleNamespace(resized=None)}
    pipes["requests"].resize = lambda n: setattr(pipes["requests"], "resized", n)
    cfg = apply_live(default_runtime_config(), pipes, {"pipelines": {"requests": {"workers": 7}}})
    assert pipes["requests"].resized == 7 and cfg.pipelines.requests.workers == 7
