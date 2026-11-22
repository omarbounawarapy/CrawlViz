"""Settings that fail validation are reported with the file or the key, in plain words."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, ValidationError

import routes.config as config_routes
from config import settings_store as store
from config.paths import RuntimePaths
from routes import config_support
from routes import run as run_routes

INVALID_STORED = '{"fetch": {"min_delay": "slow"}}'


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RuntimePaths:
    paths = RuntimePaths.under(tmp_path)
    monkeypatch.setattr(config_support, "default_runtime_paths", lambda: paths)
    monkeypatch.setattr(run_routes, "default_runtime_paths", lambda: paths)
    monkeypatch.setattr(run_routes, "_current_task", None)
    monkeypatch.setattr(run_routes, "_current_crawler", None)
    paths.settings_file.parent.mkdir(parents=True, exist_ok=True)
    return paths


@pytest.fixture
def client(paths: RuntimePaths) -> TestClient:
    app = FastAPI()
    app.include_router(config_routes.router)
    app.include_router(run_routes.router)
    return TestClient(app)


def _write_invalid_stored(paths: RuntimePaths) -> None:
    paths.settings_file.write_text(INVALID_STORED, encoding="utf-8")


def test_stored_settings_that_are_not_valid_name_the_file_and_the_key(paths: RuntimePaths) -> None:
    _write_invalid_stored(paths)
    with pytest.raises(store.SettingsFileError) as raised:
        store.load_runtime_config(paths.settings_file)
    message = str(raised.value)
    assert str(paths.settings_file) in message
    assert "fetch.min_delay" in message and "Config page" in message


def test_stored_settings_that_are_not_valid_are_not_overwritten_by_a_save(
    paths: RuntimePaths,
) -> None:
    _write_invalid_stored(paths)
    with pytest.raises(store.SettingsFileError):
        store.save_settings(paths.settings_file, {"run": {"seed": 3}})
    assert paths.settings_file.read_text(encoding="utf-8") == INVALID_STORED


def test_an_invalid_override_over_valid_stored_settings_stays_a_validation_error(
    paths: RuntimePaths,
) -> None:
    store.save_settings(paths.settings_file, {"fetch": {"min_delay": 3.0}})
    with pytest.raises(ValidationError):
        store.load_runtime_config(paths.settings_file, {"fetch": {"jitter_max": "wide"}})
    with pytest.raises(ValidationError):
        store.save_settings(paths.settings_file, {"fetch": {"jitter_max": "wide"}})


def test_an_override_can_correct_an_invalid_stored_value(paths: RuntimePaths) -> None:
    _write_invalid_stored(paths)
    config = store.load_runtime_config(paths.settings_file, {"fetch": {"min_delay": 1.5}})
    assert config.fetch.min_delay == 1.5


def test_config_route_reports_invalid_stored_settings_then_reset_repairs_them(
    client: TestClient, paths: RuntimePaths
) -> None:
    _write_invalid_stored(paths)

    response = client.get("/config")

    assert response.status_code == 422
    message = response.json()["detail"]["message"]
    assert str(paths.settings_file) in message and "fetch.min_delay" in message
    assert client.post("/config/reset").status_code == 200
    assert client.get("/config").status_code == 200


def test_a_run_with_invalid_stored_settings_says_which_file_to_fix(
    client: TestClient, paths: RuntimePaths
) -> None:
    _write_invalid_stored(paths)

    response = client.post("/run", json={"templateName": "isi.json"})

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert str(paths.settings_file) in detail and "fetch.min_delay" in detail
    assert run_routes._current_task is None


def test_a_run_with_an_invalid_override_names_the_key(client: TestClient) -> None:
    response = client.post(
        "/run", json={"templateName": "isi.json", "overrides": {"fetch": {"min_delay": "slow"}}}
    )

    assert response.status_code == 422
    assert "fetch.min_delay" in response.json()["detail"]


def test_an_unknown_key_is_described_as_a_missing_setting_not_as_extra_input() -> None:
    class Section(BaseModel):
        model_config = ConfigDict(extra="forbid")
        known: int = 0

    with pytest.raises(ValidationError) as raised:
        Section.model_validate({"unknown": 1})

    (problem,) = store.validation_errors(raised.value)
    assert problem == {"path": "unknown", "message": store.EXTRA_KEY_MESSAGE}
    assert "spelling" in problem["message"]


def test_a_config_patch_with_an_invalid_value_is_a_422_naming_the_key(client: TestClient) -> None:
    response = client.put("/config", json={"values": {"fetch": {"min_delay": "slow"}}})

    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["path"] == "fetch.min_delay"
