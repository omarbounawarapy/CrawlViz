"""GET /status reports the running crawl's LLM call budget, so the Run page can show it."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from crawlviz.llm import CallBudget
from crawlviz.telemetry import StatusBoard
from routes import run as run_routes


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(run_routes.router)
    monkeypatch.setattr(run_routes, "_current_task", None)
    monkeypatch.setattr(run_routes, "_current_crawler", None)
    monkeypatch.setattr(run_routes, "_last_outcome", None)
    monkeypatch.setattr(run_routes, "_stop_requested", False)
    return TestClient(app)


def _running(monkeypatch, crawler):
    monkeypatch.setattr(run_routes, "_current_task", SimpleNamespace(done=lambda: False))
    monkeypatch.setattr(run_routes, "_current_crawler", crawler)


def test_idle_reports_no_budget(client):
    assert client.get("/status").json() == {
        "running": False,
        "llm_calls": None,
        "queues": None,
        "last_outcome": None,
        "last_error": None,
        "crawl_state": "idle",
        "crawl_id": None,
        "board": None,
    }


def test_running_reports_calls_used_and_the_cap(client, monkeypatch):
    budget = CallBudget(5)
    budget.take(3)
    _running(monkeypatch, SimpleNamespace(call_budget=budget))
    assert client.get("/status").json() == {
        "running": True,
        "llm_calls": {"limit": 5, "used": 3, "refused": 0, "exhausted": False},
        "queues": None,
        "last_outcome": None,
        "last_error": None,
        "crawl_state": "running",
        "crawl_id": None,
        "board": None,
    }


def test_refused_calls_are_counted_once_the_cap_is_reached(client, monkeypatch):
    budget = CallBudget(5)
    budget.take(4)
    budget.take(3)
    _running(monkeypatch, SimpleNamespace(call_budget=budget))
    calls = client.get("/status").json()["llm_calls"]
    assert calls == {"limit": 5, "used": 5, "refused": 2, "exhausted": True}


def test_no_cap_reports_a_null_limit(client, monkeypatch):
    budget = CallBudget(None)
    budget.take(7)
    _running(monkeypatch, SimpleNamespace(call_budget=budget))
    calls = client.get("/status").json()["llm_calls"]
    assert calls["limit"] is None and calls["used"] == 7


def test_crawler_without_a_budget_reports_none(client, monkeypatch):
    _running(monkeypatch, SimpleNamespace())
    assert client.get("/status").json() == {
        "running": True,
        "llm_calls": None,
        "queues": None,
        "last_outcome": None,
        "last_error": None,
        "crawl_state": "running",
        "crawl_id": None,
        "board": None,
    }


def test_a_task_without_a_crawler_yet_is_starting(client, monkeypatch):
    _running(monkeypatch, None)
    assert client.get("/status").json()["crawl_state"] == "starting"


def test_a_stop_request_while_running_is_stopping(client, monkeypatch):
    _running(monkeypatch, SimpleNamespace())
    monkeypatch.setattr(run_routes, "_stop_requested", True)
    assert client.get("/status").json()["crawl_state"] == "stopping"


@pytest.mark.parametrize("ended", ["finished", "stopped", "failed"])
def test_an_ended_crawl_reports_how_it_ended(client, monkeypatch, ended):
    outcome = (
        run_routes._failed_outcome("demo.json", RuntimeError("boom"))
        if ended == "failed"
        else run_routes.CrawlOutcome("demo.json", ended)
    )
    monkeypatch.setattr(run_routes, "_last_outcome", outcome)
    reply = client.get("/status").json()
    assert (reply["running"], reply["crawl_state"], reply["last_outcome"]) == (False, ended, ended)


def test_a_running_crawl_reports_its_id_and_its_board(client, monkeypatch):
    board = StatusBoard()
    board.report("embedder", "starting", "loading_model")
    _running(monkeypatch, SimpleNamespace(crawl_id="demo-20261107", status_board=board))
    reply = client.get("/status").json()
    assert reply["crawl_id"] == "demo-20261107"
    assert reply["board"]["subsystems"]["embedder"]["reason"] == "loading_model"
    assert list(reply["board"]["subsystems"]) == list(board.snapshot().subsystems)


def test_the_board_and_id_of_an_ended_crawl_stay_until_the_next_one(client, monkeypatch):
    board = StatusBoard()
    board.report("fetch", "ready")
    ended = run_routes.CrawlOutcome(
        "demo.json", "finished", crawl_id="demo-20261107", board=board.snapshot()
    )
    monkeypatch.setattr(run_routes, "_last_outcome", ended)
    reply = client.get("/status").json()
    assert reply["crawl_id"] == "demo-20261107"
    assert reply["board"]["subsystems"]["fetch"]["state"] == "ready"


def test_the_reply_is_declared_in_the_openapi_document(client):
    paths = client.app.openapi()["paths"]
    schema = paths["/status"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/CrawlStatusReply"}
