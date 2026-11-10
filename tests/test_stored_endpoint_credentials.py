"""A settings file saved before provider endpoints were refused may hold a credential in
an endpoint URL. Loading it must clean the file instead of failing every request
(SEC-3, CONTRACT-1)."""

import json
import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routes.config as config_routes
from config import settings_store
from config.paths import RuntimePaths
from routes import config_support

PASSWORD = "pw-FAKE-0123"
FAKE_KEY = "SECRET-FAKE-0123456789"
OLD_ENDPOINT = f"https://user:{PASSWORD}@host.example/v1?key={FAKE_KEY}"
CLEAN_ENDPOINT = "https://host.example/v1"


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RuntimePaths:
    runtime_paths = RuntimePaths.under(tmp_path)
    monkeypatch.setattr(config_support, "default_runtime_paths", lambda: runtime_paths)
    return runtime_paths


@pytest.fixture
def client(paths: RuntimePaths) -> TestClient:
    app = FastAPI()
    app.include_router(config_routes.router)
    return TestClient(app)


def _store(paths: RuntimePaths, text: str) -> None:
    paths.settings_file.parent.mkdir(parents=True, exist_ok=True)
    paths.settings_file.write_text(text, encoding="utf-8")


def _store_old_endpoint(paths: RuntimePaths) -> None:
    _store(paths, json.dumps({"providers": {"endpoints": {"openai": OLD_ENDPOINT}}}))


def test_stored_endpoint_credentials_are_dropped_on_load(paths: RuntimePaths) -> None:
    _store_old_endpoint(paths)

    config = settings_store.load_runtime_config(paths.settings_file)

    assert config.providers.endpoints["openai"] == CLEAN_ENDPOINT


def test_the_settings_file_is_cleaned_on_disk(paths: RuntimePaths) -> None:
    _store_old_endpoint(paths)

    settings_store.load_runtime_config(paths.settings_file)

    on_disk = paths.settings_file.read_text(encoding="utf-8")
    assert FAKE_KEY not in on_disk
    assert PASSWORD not in on_disk
    assert json.loads(on_disk)["providers"]["endpoints"]["openai"] == CLEAN_ENDPOINT
    assert not paths.settings_file.with_suffix(".json.tmp").exists()


def test_get_config_returns_200_for_an_old_settings_file(
    client: TestClient, paths: RuntimePaths
) -> None:
    _store_old_endpoint(paths)

    response = client.get("/config")

    assert response.status_code == 200
    assert response.json()["providers"]["endpoints"]["openai"] == CLEAN_ENDPOINT
    assert FAKE_KEY not in response.text


def test_the_warning_names_the_provider_and_not_the_credential(
    paths: RuntimePaths, caplog: pytest.LogCaptureFixture
) -> None:
    _store_old_endpoint(paths)

    with caplog.at_level(logging.WARNING):
        settings_store.load_runtime_config(paths.settings_file)

    assert "openai" in caplog.text
    assert "keys" in caplog.text.lower()
    for secret in (FAKE_KEY, PASSWORD, "host.example", "user:"):
        assert secret not in caplog.text


def test_a_clean_settings_file_is_not_rewritten(paths: RuntimePaths) -> None:
    text = '{"providers": {"endpoints": {"openai": "http://localhost:11434/v1?model=llama"}}}'
    _store(paths, text)

    settings_store.load_runtime_config(paths.settings_file)

    assert paths.settings_file.read_text(encoding="utf-8") == text


def test_get_config_explains_settings_that_fail_validation(
    client: TestClient, paths: RuntimePaths
) -> None:
    _store(paths, '{"run": {"stop_check_interval": -1}}')

    response = client.get("/config")

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "settings" in detail["message"].lower()
    assert detail["errors"][0]["path"] == "run.stop_check_interval"
