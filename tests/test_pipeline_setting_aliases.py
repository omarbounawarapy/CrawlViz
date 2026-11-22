"""`pipelines.<key>` settings under their pre-ADR 6 names are still read (ADR 6)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import routes.config as config_routes
from config import settings_store as store
from config.paths import RuntimePaths
from config.runtime_config import RuntimeConfig, default_runtime_config
from core.live_settings import apply_live
from routes import config_support

OLD_AND_NEW = {"pipelines": {"requests": {"workers": 2}, "fetch": {"workers": 8}}}
BOTH_NAMES_MESSAGE = "pipelines.requests and pipelines.fetch are the same setting"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, RuntimePaths]:
    paths = RuntimePaths.under(tmp_path)
    monkeypatch.setattr(config_support, "default_runtime_paths", lambda: paths)
    app = FastAPI()
    app.include_router(config_routes.router)
    return TestClient(app), paths


def test_a_section_under_its_old_name_loads_into_the_new_field() -> None:
    config = RuntimeConfig.model_validate({"pipelines": {"requests": {"workers": 3}}})
    assert config.pipelines.fetch.workers == 3


def test_a_section_under_its_new_name_loads() -> None:
    config = RuntimeConfig.model_validate({"pipelines": {"fetch": {"workers": 3}}})
    assert config.pipelines.fetch.workers == 3


def test_every_old_name_reaches_its_new_field() -> None:
    old = {
        "processing": "extract",
        "requests": "fetch",
        "scoring": "score",
        "filtering": "filter",
        "priority": "prioritize",
        "transformation": "transform",
        "debugging": "debug_log",
    }
    config = RuntimeConfig.model_validate(
        {"pipelines": {name: {"workers": 40 + index} for index, name in enumerate(old)}}
    )
    for index, new in enumerate(old.values()):
        assert getattr(config.pipelines, new).workers == 40 + index


def test_one_section_under_both_names_is_refused_and_names_both_keys() -> None:
    with pytest.raises(ValidationError) as raised:
        RuntimeConfig.model_validate(OLD_AND_NEW)
    message = str(raised.value)
    assert BOTH_NAMES_MESSAGE in message
    assert "Keep only pipelines.fetch." in message


def test_an_unknown_section_still_fails_with_its_path() -> None:
    with pytest.raises(ValidationError) as raised:
        RuntimeConfig.model_validate({"pipelines": {"fetchh": {"workers": 2}}})
    assert [tuple(problem["loc"]) for problem in raised.value.errors()] == [("pipelines", "fetchh")]


def test_a_settings_file_with_old_names_loads_and_is_saved_with_the_new_names(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text('{"pipelines": {"requests": {"workers": 3}}}', encoding="utf-8")

    assert store.load_runtime_config(settings_file).pipelines.fetch.workers == 3

    store.save_settings(settings_file, {"fetch": {"min_delay": 3.0}})
    assert store.read_stored(settings_file)["pipelines"] == {"fetch": {"workers": 3}}


def test_a_settings_file_with_both_names_is_refused_naming_the_file(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps(OLD_AND_NEW), encoding="utf-8")

    with pytest.raises(store.SettingsFileError, match=BOTH_NAMES_MESSAGE) as raised:
        store.load_runtime_config(settings_file)
    assert str(settings_file) in str(raised.value)


def test_a_rest_patch_with_old_names_is_applied_and_stored_under_the_new_names(
    client: tuple[TestClient, RuntimePaths],
) -> None:
    c, paths = client

    response = c.put("/config", json={"values": {"pipelines": {"filtering": {"workers": 5}}}})

    assert response.status_code == 200
    assert response.json()["pipelines"]["filter"]["workers"] == 5
    assert store.read_stored(paths.settings_file)["pipelines"] == {"filter": {"workers": 5}}


@pytest.mark.parametrize(
    ("method", "route"),
    [("put", "/config"), ("put", "/config/replace"), ("post", "/config/effective")],
)
def test_a_rest_patch_with_both_names_is_refused_naming_both_keys(
    client: tuple[TestClient, RuntimePaths], method: str, route: str
) -> None:
    c, _ = client

    response = getattr(c, method)(route, json={"values": OLD_AND_NEW})

    assert response.status_code == 422
    (problem,) = response.json()["detail"]["errors"]
    assert problem["path"] == "pipelines" and BOTH_NAMES_MESSAGE in problem["message"]


def test_the_validate_route_reports_both_names_without_failing(
    client: tuple[TestClient, RuntimePaths],
) -> None:
    c, _ = client

    body = c.post("/config/validate", json={"values": OLD_AND_NEW}).json()

    assert body["valid"] is False and BOTH_NAMES_MESSAGE in body["errors"][0]["message"]


def test_a_live_patch_with_an_old_name_resizes_the_stage() -> None:
    resized: list[int] = []
    stages = {"requests": SimpleNamespace(resize=resized.append)}

    config = apply_live(
        default_runtime_config(), stages, {"pipelines": {"requests": {"workers": 7}}}
    )

    assert resized == [7] and config.pipelines.fetch.workers == 7
