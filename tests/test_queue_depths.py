"""Queue depths of a running crawl: what the Pipelines picture shows while a crawl runs."""
import asyncio
from types import SimpleNamespace

from core.crawler import Crawler


def _stage(maxsize=0, items=0):
    queue = asyncio.Queue(maxsize=maxsize)
    for i in range(items):
        queue.put_nowait(i)
    return SimpleNamespace(queue=queue)


def test_queue_depths_name_each_stage_by_its_setting():
    fake = SimpleNamespace(_pipelines={
        "requests": _stage(maxsize=10, items=3),
        "debug": _stage(items=2),
        "logging": _stage(items=5),  # not a settings stage, so not reported
    })
    depths = Crawler.queue_depths(fake)
    assert depths["requests"] == {"size": 3, "max": 10}
    assert depths["debugging"] == {"size": 2, "max": None}
    assert "logging" not in depths


def test_queue_depths_is_empty_before_a_crawl_has_pipelines():
    assert Crawler.queue_depths(SimpleNamespace(_pipelines={})) == {}


def test_status_reports_queues_only_while_running(monkeypatch):
    from routes import run as run_routes

    class Running:
        def queue_depths(self):
            return {"fetch": {"size": 1, "max": None}}

    monkeypatch.setattr(run_routes, "_current_crawler", Running())
    monkeypatch.setattr(run_routes, "_current_task", SimpleNamespace(done=lambda: False))
    assert run_routes.crawl_status()["queues"] == {"fetch": {"size": 1, "max": None}}

    monkeypatch.setattr(run_routes, "_current_task", SimpleNamespace(done=lambda: True))
    assert run_routes.crawl_status()["queues"] is None
