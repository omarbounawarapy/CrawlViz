"""A refused settings value comes back to the browser in a 422 body, so the error list
must hold the field path and a message, never the submitted value (SEC-3)."""

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import routes.config as config_routes
from config.paths import RuntimePaths
from config.runtime_config import RuntimeConfig
from routes import config_support

FAKE_KEY = "FAKEKEY-0123456789"
REFUSED_ENDPOINT = f"https://user:hunter2@api.example/v1?key={FAKE_KEY}"
REFUSED_VALUES = {"values": {"providers": {"endpoints": {"openai": REFUSED_ENDPOINT}}}}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    paths = RuntimePaths.under(tmp_path)
    monkeypatch.setattr(config_support, "default_runtime_paths", lambda: paths)
    app = FastAPI()
    app.include_router(config_routes.router)
    return TestClient(app)


def test_a_refused_endpoint_is_not_echoed_in_the_422_body(client: TestClient) -> None:
    response = client.put("/config", json=REFUSED_VALUES)

    assert response.status_code == 422
    assert "openai endpoint must not contain" in response.text
    assert FAKE_KEY not in response.text
    assert "hunter2" not in response.text


def test_a_refused_endpoint_is_not_echoed_by_the_validate_route(client: TestClient) -> None:
    response = client.post("/config/validate", json=REFUSED_VALUES)

    assert response.json()["valid"] is False
    assert FAKE_KEY not in response.text
    assert "hunter2" not in response.text


def test_validation_errors_ask_pydantic_to_leave_out_the_input_and_the_url() -> None:
    """The submitted value is one keyword away from every error; it is never requested."""
    requested: list[dict[str, Any]] = []

    class _Error:
        def errors(self, **options: Any) -> list[dict[str, Any]]:
            requested.append(options)
            entry: dict[str, Any] = {"loc": ("fetch", "min_delay"), "msg": "too small"}
            if options.get("include_input", True):
                entry["input"] = FAKE_KEY
            if options.get("include_url", True):
                entry["url"] = f"https://errors.pydantic.dev/{FAKE_KEY}"
            return [entry]

    errors = config_support.validation_errors(_Error())  # type: ignore[arg-type]

    assert requested == [{"include_input": False, "include_url": False}]
    assert errors == [{"path": "fetch.min_delay", "message": "too small"}]


def test_the_real_error_list_carries_no_input() -> None:
    with pytest.raises(ValidationError) as caught:
        RuntimeConfig.model_validate(REFUSED_VALUES["values"])

    assert FAKE_KEY not in str(config_support.validation_errors(caught.value))
