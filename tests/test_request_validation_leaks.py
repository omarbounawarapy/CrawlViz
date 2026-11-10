"""FastAPI's default 422 echoes the request body, so a submitted key with one missing field
would come back in the response. The app answers with the field path and message only
(SEC-3)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config.paths import RuntimePaths
from main import app
from routes import config_support
from routes.session_token import TOKEN_ENV_VAR

FAKE_KEY = "FAKEKEY-0123456789"
API_TOKEN = "test-session-token"
REFUSED_ENDPOINT = f"https://user:hunter2@api.example/v1?key={FAKE_KEY}"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    paths = RuntimePaths.under(tmp_path)
    monkeypatch.setattr(config_support, "default_runtime_paths", lambda: paths)
    monkeypatch.setenv(TOKEN_ENV_VAR, API_TOKEN)
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    return TestClient(app, base_url="http://localhost", headers=headers)


def test_a_keys_request_missing_a_field_does_not_echo_the_submitted_key(
    client: TestClient,
) -> None:
    response = client.post("/keys", json={"key": FAKE_KEY})

    assert response.status_code == 422
    assert FAKE_KEY not in response.text
    assert response.json() == {
        "detail": {"errors": [{"path": "body.provider", "message": "Field required"}]}
    }


def test_a_wrong_type_does_not_echo_the_submitted_value_or_the_docs_url(
    client: TestClient,
) -> None:
    response = client.post("/keys", json={"provider": "groq", "key": [FAKE_KEY]})

    assert response.status_code == 422
    assert FAKE_KEY not in response.text
    assert "errors.pydantic.dev" not in response.text


def test_a_config_route_keeps_its_422_shape(client: TestClient) -> None:
    refused = {"values": {"providers": {"endpoints": {"openai": REFUSED_ENDPOINT}}}}

    response = client.put("/config", json=refused)

    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    assert errors and set(errors[0]) == {"path", "message"}
    assert FAKE_KEY not in response.text
