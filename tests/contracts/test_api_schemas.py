"""The API reply models describe what the routes return today, so declaring them as
``response_model`` changes no existing key (CONTRACT-2)."""

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from crawlviz.api.schemas import (
    CrawlStatusReply,
    HealthReply,
    LlmCallsSnapshot,
    ReadinessCheck,
    ReadyReply,
)
from crawlviz.contracts import initial_board
from crawlviz.llm import CallBudget
from routes import health as health_routes
from routes import run as run_routes

ADDED_BY_THE_BOARD = {"crawl_state", "crawl_id", "board"}


@pytest.fixture
def status_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = FastAPI()
    app.include_router(run_routes.router)
    monkeypatch.setattr(run_routes, "_current_task", None)
    monkeypatch.setattr(run_routes, "_current_crawler", None)
    monkeypatch.setattr(run_routes, "_last_outcome", None)
    return TestClient(app)


def _running(monkeypatch: pytest.MonkeyPatch, crawler: object) -> None:
    monkeypatch.setattr(run_routes, "_current_task", SimpleNamespace(done=lambda: False))
    monkeypatch.setattr(run_routes, "_current_crawler", crawler)


def _without_descriptions(schema: Any) -> Any:
    """A JSON Schema with its docstring-derived descriptions removed, at every level."""
    if isinstance(schema, dict):
        return {k: _without_descriptions(v) for k, v in schema.items() if k != "description"}
    if isinstance(schema, list):
        return [_without_descriptions(item) for item in schema]
    return schema


def _assert_describes(reply: dict[str, Any]) -> None:
    """The model accepts the reply and gives back the same keys and values."""
    parsed = CrawlStatusReply.model_validate(reply)
    assert parsed.model_dump(exclude=ADDED_BY_THE_BOARD) == reply


@pytest.mark.parametrize(
    ("route_model", "schema_model"),
    [
        (health_routes.HealthReply, HealthReply),
        (health_routes.ReadinessCheck, ReadinessCheck),
        (health_routes.ReadyReply, ReadyReply),
    ],
)
def test_health_replies_match_the_router_copies(
    route_model: type[BaseModel], schema_model: type[BaseModel]
) -> None:
    assert _without_descriptions(schema_model.model_json_schema()) == _without_descriptions(
        route_model.model_json_schema()
    )


@pytest.mark.parametrize("limit", [5, None])
def test_the_llm_calls_model_keeps_the_budget_snapshot_shape(limit: int | None) -> None:
    budget = CallBudget(limit)
    budget.take(7)

    snapshot = budget.snapshot()

    assert LlmCallsSnapshot.model_validate(snapshot).model_dump() == snapshot


def test_the_idle_reply_is_described(status_client: TestClient) -> None:
    _assert_describes(status_client.get("/status").json())


def test_a_running_reply_with_budget_and_queues_is_described(
    status_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    budget = CallBudget(5)
    budget.take(3)
    queues = {"fetch": {"size": 2, "max": 50}, "score": {"size": 0, "max": None}}
    _running(monkeypatch, SimpleNamespace(call_budget=budget, queue_depths=lambda: queues))

    _assert_describes(status_client.get("/status").json())


def test_a_failed_crawl_reply_is_described(
    status_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure = run_routes._failed_outcome("demo.json", RuntimeError("secret"))
    monkeypatch.setattr(run_routes, "_last_outcome", failure)

    reply = status_client.get("/status").json()

    _assert_describes(reply)
    assert CrawlStatusReply.model_validate(reply).last_outcome == "failed"


def test_as_response_model_it_only_adds_the_board_keys() -> None:
    v1_reply = {
        "running": False,
        "llm_calls": None,
        "queues": None,
        "last_outcome": "finished",
        "last_error": None,
    }
    app = FastAPI()

    @app.get("/status", response_model=CrawlStatusReply)
    def crawl_status() -> dict[str, Any]:
        return v1_reply

    reply = TestClient(app).get("/status").json()

    assert reply == {**v1_reply, **dict.fromkeys(ADDED_BY_THE_BOARD)}


def test_the_board_fits_in_the_reply() -> None:
    reply = CrawlStatusReply(
        running=True,
        llm_calls=None,
        queues=None,
        last_outcome=None,
        last_error=None,
        crawl_state="starting",
        crawl_id="run-1",
        board=initial_board(1_000.0),
    )

    assert CrawlStatusReply.model_validate_json(reply.model_dump_json()) == reply


def test_unknown_keys_are_refused() -> None:
    with pytest.raises(ValueError, match="extra"):
        CrawlStatusReply.model_validate(
            {
                "running": False,
                "llm_calls": None,
                "queues": None,
                "last_outcome": None,
                "last_error": None,
                "mode": "offline",
            }
        )
