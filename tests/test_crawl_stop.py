"""Stopping a crawl by hand ends it in two phases and never leaves the gateway
port bound, the event log open or the semantic space buffer unsaved."""

import asyncio
import json
import socket
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.paths import RuntimePaths
from config.runtime_config import default_runtime_config
from core.crawler import Crawler
from nlp import BufferManager, SpaceUpdater
from routes import run as run_routes
from tests.test_event_wiring import FAKE_BLUEPRINT, Fake
from ui_bridge import CrawlStateSnapshot, UIWebSocketGateway
from ui_bridge.event_recorder import EventRecorder

STARTUP_WAIT_SECONDS = 10
FINISH_WAIT_SECONDS = 15
POLL_SECONDS = 0.01
BUFFERED_VECTOR_COUNT = 3
VECTOR_DIM = 4
STUB_GRACE_SECONDS = 0.05


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _can_bind(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(("localhost", port))
        except OSError:
            return False
    return True


async def _until(condition: Callable[[], bool]) -> None:
    async def poll() -> None:
        while not condition():
            await asyncio.sleep(POLL_SECONDS)

    await asyncio.wait_for(poll(), STARTUP_WAIT_SECONDS)


class _Fetcher:
    """A page fetcher that is never asked for a page."""

    async def emit_request(self, params: dict[str, Any]) -> str:
        raise AssertionError("no page should be requested")

    async def close(self) -> None:
        pass


class _SpaceOwner:
    """What SpaceUpdater needs from the service that owns the space."""

    def __init__(self) -> None:
        self.space: Any = SimpleNamespace(
            add_vector=self._add, version=0
        )  # stands in for VectorSpace
        self.added: list[str] = []
        self.saves = 0

    def _add(self, key: str, vector: object, metadata: object) -> None:
        self.added.append(key)

    def save_space(self) -> None:
        self.saves += 1

    def space_size(self) -> int:
        return len(self.added)


class _CrawlHarness:
    """A real Crawler whose NLP subsystem is replaced by inert doubles."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.port = _free_port()
        self.paths = RuntimePaths.under(tmp_path)
        self.owner = _SpaceOwner()
        self.buffer = BufferManager()
        self.recorder_closes = 0
        self.crawler = Crawler(
            "wikiMD.json",
            config=default_runtime_config(),
            paths=self.paths,
            ui_port=self.port,
            llm=Fake(),
            fetcher=_Fetcher(),
        )
        updater = SpaceUpdater(self.owner, self.buffer, flush_interval=3600)

        async def build_nlp(traced_llm: object, tracer: object) -> tuple[Fake, SpaceUpdater, Fake]:
            return Fake(), updater, Fake()

        monkeypatch.setattr(self.crawler, "_build_nlp_subsystem", build_nlp)
        real_close = EventRecorder.close

        def counting_close(recorder: EventRecorder) -> None:
            self.recorder_closes += 1
            real_close(recorder)

        monkeypatch.setattr(EventRecorder, "close", counting_close)
        self.crawler._load_blueprint_config(FAKE_BLUEPRINT)

    async def buffer_vectors(self) -> None:
        vector = np.zeros(VECTOR_DIM, dtype=np.float32)
        for i in range(BUFFERED_VECTOR_COUNT):
            await self.buffer.add(f"k{i}", vector, {})

    @property
    def events(self) -> list[dict[str, Any]]:  # parsed JSON lines
        path = self.paths.export_dir / self.crawler.crawl_id / "events.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()]

    async def start(self) -> asyncio.Task[None]:
        task = asyncio.create_task(self.crawler._run_session(FAKE_BLUEPRINT))
        await _until(lambda: not _can_bind(self.port))
        return task


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _CrawlHarness:
    return _CrawlHarness(tmp_path, monkeypatch)


async def test_gateway_releases_its_port_when_cancelled() -> None:
    port = _free_port()
    gateway = UIWebSocketGateway(CrawlStateSnapshot(), port=port)
    task = asyncio.create_task(gateway.start())
    await _until(lambda: not _can_bind(port))

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert _can_bind(port)


async def test_cancelled_crawl_frees_the_port_closes_the_log_and_saves_the_space(
    harness: _CrawlHarness,
) -> None:
    task = await harness.start()
    await harness.buffer_vectors()

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert _can_bind(harness.port)
    assert harness.recorder_closes >= 1
    assert harness.owner.added == ["k0", "k1", "k2"] and harness.owner.saves == 1


async def test_requested_stop_ends_the_crawl_on_its_own_and_records_why(
    harness: _CrawlHarness,
) -> None:
    task = await harness.start()

    assert await harness.crawler.request_stop()
    await asyncio.wait_for(task, FINISH_WAIT_SECONDS)

    stopped = [m for m in harness.events if m["type"] == "CRAWL_STOPPED"]
    assert [m["reason"] for m in stopped] == ["MANUAL_STOP"]
    assert _can_bind(harness.port)


async def test_stop_request_before_the_stages_exist_is_declined() -> None:
    crawler = Crawler("wikiMD.json", llm=Fake(), fetcher=Fake())
    assert not await crawler.request_stop()


class _StubCrawler:
    """Finishes its task when asked to stop, or ignores the request."""

    def __init__(self, release: asyncio.Event, obeys: bool) -> None:
        self.config = SimpleNamespace(run=SimpleNamespace(shutdown_grace=STUB_GRACE_SECONDS))
        self._release = release
        self._obeys = obeys
        self.asked = False

    async def request_stop(self) -> bool:
        self.asked = True
        if self._obeys:
            self._release.set()
        return True


def _install_running_task(
    monkeypatch: pytest.MonkeyPatch, obeys: bool
) -> tuple[asyncio.Task[None], _StubCrawler, dict[str, bool]]:
    release = asyncio.Event()
    crawler = _StubCrawler(release, obeys)
    outcome = {"cancelled": False, "cleaned": False}

    async def body() -> None:
        try:
            await release.wait()
        except asyncio.CancelledError:
            outcome["cancelled"] = True
            await asyncio.sleep(0)  # cleanup that needs one more loop turn
            outcome["cleaned"] = True
            raise

    task = asyncio.get_running_loop().create_task(body())
    monkeypatch.setattr(run_routes, "_current_task", task)
    monkeypatch.setattr(run_routes, "_current_crawler", crawler)
    monkeypatch.setattr(run_routes, "STOP_DRAIN_MARGIN_SECONDS", STUB_GRACE_SECONDS)
    return task, crawler, outcome


async def test_stop_route_waits_for_a_graceful_finish(monkeypatch: pytest.MonkeyPatch) -> None:
    task, crawler, outcome = _install_running_task(monkeypatch, obeys=True)
    await asyncio.sleep(0)

    body = await run_routes.stop_crawl()

    assert task.done() and not task.cancelled()
    assert crawler.asked and not outcome["cancelled"]
    assert body == {"stopped": True, "graceful": True}


async def test_stop_route_cancels_and_awaits_a_crawl_that_ignores_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task, _, outcome = _install_running_task(monkeypatch, obeys=False)
    await asyncio.sleep(0)

    body = await run_routes.stop_crawl()

    assert task.done() and outcome["cleaned"]
    assert body == {"stopped": True, "graceful": False}


def test_stop_route_with_nothing_running_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.include_router(run_routes.router)
    monkeypatch.setattr(run_routes, "_current_task", None)
    reply = TestClient(app).post("/stop").json()
    assert reply["stopped"] is False
