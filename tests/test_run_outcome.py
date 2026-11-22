"""A crawl that fails is recorded and reported by GET /status, never dropped."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.runtime_config import RuntimeConfig, default_runtime_config
from routes import run as run_routes


class _Crawler:
    """Stands in for Crawler: `start` runs `behaviour`."""

    behaviour: Exception | None = None

    def __init__(
        self, template_name: str, config: RuntimeConfig | None = None, seed: int | None = None
    ) -> None:
        self.template_name = template_name

    async def start(self) -> None:
        if _Crawler.behaviour is not None:
            raise _Crawler.behaviour


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(run_routes, "is_offline", lambda: False)
    monkeypatch.setattr(run_routes, "Crawler", _Crawler)
    monkeypatch.setattr(run_routes, "_current_task", None)
    monkeypatch.setattr(run_routes, "_current_crawler", None)
    monkeypatch.setattr(run_routes, "_last_outcome", None)
    monkeypatch.setattr(run_routes, "_stop_requested", False)
    _Crawler.behaviour = None
    yield
    _Crawler.behaviour = None


def _status() -> dict[str, Any]:  # the parsed /status JSON body
    app = FastAPI()
    app.include_router(run_routes.router)
    status: dict[str, Any] = TestClient(app).get("/status").json()
    return status


async def _run() -> None:
    await run_routes._run_crawler("wikiMD.json", config=default_runtime_config())


async def test_failed_crawl_is_reported_with_a_plain_message() -> None:
    _Crawler.behaviour = ValueError("secret=abc123 in https://example.org/?key=abc123")

    await _run()

    status = _status()
    assert status["last_outcome"] == "failed"
    assert status["last_error"]["error_type"] == "ValueError"
    message = status["last_error"]["message"]
    assert "wikiMD.json" in message and "start the crawl again" in message
    assert "abc123" not in message


async def test_finished_crawl_has_no_error() -> None:
    await _run()

    assert _status()["last_outcome"] == "finished"
    assert _status()["last_error"] is None


async def test_crawl_ended_by_a_stop_request_is_reported_as_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_routes, "_stop_requested", True)

    await _run()

    assert _status()["last_outcome"] == "stopped"
