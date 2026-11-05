"""`GET /health`: liveness, behind the same guards as every route."""

import pytest
from fastapi.testclient import TestClient

import main
from routes.session_token import get_session_token


@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app, base_url="http://localhost:8000")


@pytest.fixture
def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_session_token()}"}


def test_health_reports_the_process_is_up(client: TestClient, headers: dict[str, str]) -> None:
    reply = client.get("/health", headers=headers)
    assert reply.status_code == 200
    assert reply.json() == {"status": "ok"}


def test_health_needs_the_session_token(client: TestClient) -> None:
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_health_refuses_a_foreign_host_or_origin(
    client: TestClient, headers: dict[str, str]
) -> None:
    assert client.get("/health", headers={**headers, "Host": "evil.example"}).status_code == 421
    refused = client.get("/health", headers={**headers, "Origin": "https://evil.example"})
    assert refused.status_code == 403
