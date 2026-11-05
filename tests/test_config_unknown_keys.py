"""Config models refuse keys they do not have, so a misspelt or unmigrated key is never lost."""

import inspect
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

import routes.config as config_routes
from config import runtime_config
from config.paths import RuntimePaths
from config.runtime_config import RuntimeConfig, default_runtime_config
from config.settings_store import SettingsFileError, load_runtime_config
from routes import config_support
from routes import run as run_routes


def _model_classes() -> list[type[BaseModel]]:
    return [
        cls
        for _, cls in inspect.getmembers(runtime_config, inspect.isclass)
        if issubclass(cls, BaseModel)
        and cls is not BaseModel
        and cls.__module__ == runtime_config.__name__
    ]


def _locations(error: ValidationError) -> list[tuple[str | int, ...]]:
    return [tuple(entry["loc"]) for entry in error.errors()]


@pytest.mark.parametrize("model", _model_classes(), ids=lambda model: model.__name__)
def test_every_config_model_forbids_unknown_keys(model: type[BaseModel]) -> None:
    assert model.model_config.get("extra") == "forbid"


def test_there_are_config_models_to_check() -> None:
    assert RuntimeConfig in _model_classes() and len(_model_classes()) > 10


def test_an_unknown_top_level_key_is_refused_by_name() -> None:
    with pytest.raises(ValidationError) as raised:
        RuntimeConfig.model_validate({"bogus": 1})
    assert _locations(raised.value) == [("bogus",)]


def test_an_unknown_section_key_names_its_whole_path() -> None:
    with pytest.raises(ValidationError) as raised:
        load_runtime_config(None, {"pipelines": {"fetchh": {"workers": 2}}})
    assert _locations(raised.value) == [("pipelines", "fetchh")]


def test_an_unknown_key_two_levels_down_names_its_whole_path() -> None:
    with pytest.raises(ValidationError) as raised:
        load_runtime_config(None, {"pipelines": {"requests": {"workerz": 2}}})
    assert _locations(raised.value) == [("pipelines", "requests", "workerz")]


def test_every_unknown_key_is_reported_not_only_the_first() -> None:
    with pytest.raises(ValidationError) as raised:
        load_runtime_config(None, {"pipelines": {"fetch": {"workers": 2}}, "bogus": 1})
    assert sorted(_locations(raised.value)) == [("bogus",), ("pipelines", "fetch")]


def test_the_defaults_survive_a_round_trip() -> None:
    defaults = default_runtime_config()
    assert RuntimeConfig.model_validate(defaults.model_dump()) == defaults


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


def test_an_unknown_key_in_the_stored_file_names_the_file_and_the_key(paths: RuntimePaths) -> None:
    paths.settings_file.write_text('{"pipelines": {"fetchh": {"workers": 2}}}', encoding="utf-8")
    with pytest.raises(SettingsFileError) as raised:
        load_runtime_config(paths.settings_file)
    message = str(raised.value)
    assert str(paths.settings_file) in message
    assert "pipelines.fetchh" in message and "Config page" in message


def test_the_config_route_reports_an_unknown_stored_key_then_reset_repairs_it(
    client: TestClient, paths: RuntimePaths
) -> None:
    paths.settings_file.write_text('{"bogus": 1}', encoding="utf-8")
    response = client.get("/config")
    assert response.status_code == 500 and "bogus" in response.json()["detail"]
    assert client.post("/config/reset").status_code == 200


def test_a_config_patch_with_an_unknown_key_is_a_422_that_says_what_to_do(
    client: TestClient, paths: RuntimePaths
) -> None:
    response = client.put("/config", json={"values": {"pipelines": {"fetchh": {"workers": 2}}}})
    assert response.status_code == 422
    (problem,) = response.json()["detail"]["errors"]
    assert problem["path"] == "pipelines.fetchh"
    assert "spelling" in problem["message"] and "Extra inputs" not in problem["message"]
    assert not paths.settings_file.exists()


def test_the_validate_route_lists_the_unknown_key(client: TestClient) -> None:
    result = client.post("/config/validate", json={"values": {"bogus": 1}}).json()
    assert result["valid"] is False
    assert [problem["path"] for problem in result["errors"]] == ["bogus"]


def test_a_run_override_with_an_unknown_key_names_it(client: TestClient) -> None:
    response = client.post(
        "/run", json={"templateName": "isi.json", "overrides": {"fetch": {"min_dalay": 1.0}}}
    )
    assert response.status_code == 422
    assert "fetch.min_dalay" in response.json()["detail"]


def test_saving_a_preset_with_an_unknown_key_is_refused(client: TestClient) -> None:
    response = client.put("/config/presets/mine", json={"values": {"bogus": {"a": 1}}})
    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["path"] == "bogus"
