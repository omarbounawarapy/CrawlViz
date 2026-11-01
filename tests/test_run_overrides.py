"""Per-run overrides cannot redirect an LLM provider (its requests carry the API key)."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import run as run_routes

ENDPOINT_OVERRIDES = [
    {"providers": {"endpoints": {"openai": "http://attacker.example/v1"}}},
    {"providers": {"endpoints": {}}},
    {"fetch": {"min_delay": 1.0}, "providers": {"endpoints": {"groq": "https://example.org"}}},
]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(run_routes, "_current_task", None)
    monkeypatch.setattr(run_routes, "_current_crawler", None)
    app = FastAPI()
    app.include_router(run_routes.router)
    return TestClient(app)


@pytest.mark.parametrize("overrides", ENDPOINT_OVERRIDES)
def test_run_refuses_provider_endpoints_in_overrides(
    client: TestClient, overrides: dict[str, Any]
) -> None:
    response = client.post("/run", json={"templateName": "isi.json", "overrides": overrides})
    assert response.status_code == 422
    assert "Configuration page" in response.json()["detail"]
    assert run_routes._current_task is None


def test_other_overrides_are_not_refused_by_the_endpoint_check(client: TestClient) -> None:
    # The template does not exist, so a 404 shows the endpoint check let the request through.
    response = client.post(
        "/run", json={"templateName": "missing.json", "overrides": {"fetch": {"min_delay": 1.0}}}
    )
    assert response.status_code == 404
