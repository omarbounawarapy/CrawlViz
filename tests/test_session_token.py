"""The session token: where it comes from and how the UI reads it."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import session_token
from routes.session_token import (
    TOKEN_ENV_VAR,
    SessionTokenMiddleware,
    authorization_matches,
    get_session_token,
)


@pytest.fixture(autouse=True)
def no_environment_token(monkeypatch):
    monkeypatch.delenv(TOKEN_ENV_VAR, raising=False)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(session_token.router)
    return TestClient(app)


def test_a_token_is_generated_when_none_is_configured():
    token = get_session_token()
    assert len(token) >= 32
    assert get_session_token() == token


def test_the_environment_token_wins(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV_VAR, "from-env")
    assert get_session_token() == "from-env"


def test_authorization_matches_only_the_session_token(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV_VAR, "s3cret")
    assert authorization_matches("Bearer s3cret")
    assert not authorization_matches("Bearer nope")
    assert not authorization_matches("s3cret")
    assert not authorization_matches("")
    assert not authorization_matches(None)


def test_session_serves_the_generated_token(client):
    reply = client.get("/session")
    assert reply.status_code == 200
    assert reply.json() == {"token": get_session_token()}


def test_session_does_not_serve_a_token_set_in_the_environment(client, monkeypatch):
    monkeypatch.setenv(TOKEN_ENV_VAR, "s3cret")
    reply = client.get("/session")
    assert reply.status_code == 404
    assert "s3cret" not in reply.text
    assert "VITE_API_TOKEN" in reply.json()["detail"]


@pytest.fixture
def guarded_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(SessionTokenMiddleware)
    app.include_router(session_token.router)

    @app.get("/config")
    def read_config() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/stop")
    def stop() -> dict[str, bool]:
        return {"stopped": True}

    @app.get("/keys")
    def read_keys() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


@pytest.mark.parametrize(
    ("method", "path"), [("GET", "/config"), ("POST", "/stop"), ("GET", "/keys")]
)
def test_a_request_without_the_token_gets_401(guarded_client, method, path):
    reply = guarded_client.request(method, path)
    assert reply.status_code == 401
    assert reply.headers["www-authenticate"] == "Bearer"


def test_a_wrong_token_gets_401(guarded_client):
    reply = guarded_client.get("/config", headers={"Authorization": "Bearer nope"})
    assert reply.status_code == 401


def test_the_generated_token_opens_every_route(guarded_client):
    headers = {"Authorization": f"Bearer {get_session_token()}"}
    assert guarded_client.get("/config", headers=headers).status_code == 200
    assert guarded_client.post("/stop", headers=headers).status_code == 200


def test_the_environment_token_replaces_the_generated_one(guarded_client, monkeypatch):
    generated = {"Authorization": f"Bearer {get_session_token()}"}
    monkeypatch.setenv(TOKEN_ENV_VAR, "s3cret")
    assert guarded_client.get("/config", headers=generated).status_code == 401
    accepted = guarded_client.get("/config", headers={"Authorization": "Bearer s3cret"})
    assert accepted.status_code == 200


@pytest.mark.parametrize("path", ["/session", "/openapi.json", "/docs"])
def test_session_and_documentation_need_no_token(guarded_client, path):
    assert guarded_client.get(path).status_code == 200


def test_the_real_app_requires_the_token_on_every_router():
    from main import app

    client = TestClient(app, base_url="http://localhost:8000")
    paths = ["/templates", "/config", "/status", "/keys", "/benchmark/runs", "/validation/tables"]
    for path in paths:
        assert client.get(path).status_code == 401, path
    reply = client.get("/session")
    assert reply.status_code == 200
    headers = {"Authorization": f"Bearer {reply.json()['token']}"}
    assert client.get("/status", headers=headers).status_code == 200
