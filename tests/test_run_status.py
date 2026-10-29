"""GET /status reports the running crawl's LLM call budget, so the Run page can show it."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from infrastructure.call_budget import CallBudget
from routes import run as run_routes


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(run_routes.router)
    monkeypatch.setattr(run_routes, "_current_task", None)
    monkeypatch.setattr(run_routes, "_current_crawler", None)
    return TestClient(app)


def _running(monkeypatch, crawler):
    monkeypatch.setattr(run_routes, "_current_task", SimpleNamespace(done=lambda: False))
    monkeypatch.setattr(run_routes, "_current_crawler", crawler)


def test_idle_reports_no_budget(client):
    assert client.get("/status").json() == {"running": False, "llm_calls": None, "queues": None}


def test_running_reports_calls_used_and_the_cap(client, monkeypatch):
    budget = CallBudget(5)
    budget.take(3)
    _running(monkeypatch, SimpleNamespace(call_budget=budget))
    assert client.get("/status").json() == {
        "running": True,
        "llm_calls": {"limit": 5, "used": 3, "refused": 0, "exhausted": False},
        "queues": None,
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
    assert client.get("/status").json() == {"running": True, "llm_calls": None, "queues": None}
