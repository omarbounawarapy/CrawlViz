"""The session token: where it comes from and how the UI reads it."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import session_token
from routes.session_token import TOKEN_ENV_VAR, authorization_matches, get_session_token


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
