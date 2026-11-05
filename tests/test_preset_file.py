"""presets.json is a versioned file: saves stamp it, old files load, newer files are refused."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routes.config as config_routes
from config.paths import RuntimePaths
from routes import config_support

PRESET_VALUES = {"fetch": {"min_delay": 4.0}}


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RuntimePaths:
    runtime_paths = RuntimePaths.under(tmp_path)
    monkeypatch.setattr(config_support, "default_runtime_paths", lambda: runtime_paths)
    runtime_paths.settings_file.parent.mkdir(parents=True, exist_ok=True)
    return runtime_paths


@pytest.fixture
def client(paths: RuntimePaths) -> TestClient:
    app = FastAPI()
    app.include_router(config_routes.router)
    return TestClient(app)


def _presets_file(paths: RuntimePaths) -> Path:
    return paths.settings_file.with_name("presets.json")


def test_saved_presets_are_nested_under_one_key_with_the_version(
    client: TestClient, paths: RuntimePaths
) -> None:
    assert client.put("/config/presets/mine", json={"values": PRESET_VALUES}).status_code == 200
    stored = json.loads(_presets_file(paths).read_text(encoding="utf-8"))
    assert stored == {"schema_version": 1, "presets": {"mine": PRESET_VALUES}}


def test_an_unversioned_presets_file_still_lists_its_presets(
    client: TestClient, paths: RuntimePaths
) -> None:
    _presets_file(paths).write_text(json.dumps({"mine": PRESET_VALUES}), encoding="utf-8")
    assert client.get("/config/presets").json()["user"] == {"mine": PRESET_VALUES}


def test_saving_next_to_an_unversioned_preset_keeps_it(
    client: TestClient, paths: RuntimePaths
) -> None:
    _presets_file(paths).write_text(json.dumps({"old": PRESET_VALUES}), encoding="utf-8")
    client.put("/config/presets/new", json={"values": {"fetch": {"min_delay": 5.0}}})
    stored = json.loads(_presets_file(paths).read_text(encoding="utf-8"))
    assert set(stored["presets"]) == {"old", "new"}


def test_deleting_a_preset_rewrites_the_versioned_file(
    client: TestClient, paths: RuntimePaths
) -> None:
    client.put("/config/presets/mine", json={"values": PRESET_VALUES})
    assert client.delete("/config/presets/mine").status_code == 200
    stored = json.loads(_presets_file(paths).read_text(encoding="utf-8"))
    assert stored == {"schema_version": 1, "presets": {}}


def test_a_newer_presets_file_is_refused_and_left_alone(
    client: TestClient, paths: RuntimePaths
) -> None:
    text = json.dumps({"schema_version": 99, "presets": {}})
    _presets_file(paths).write_text(text, encoding="utf-8")
    listed = client.get("/config/presets")
    assert listed.status_code == 500
    assert "Update CrawlViz" in listed.json()["detail"]
    saved = client.put("/config/presets/mine", json={"values": PRESET_VALUES})
    assert saved.status_code == 500
    assert _presets_file(paths).read_text(encoding="utf-8") == text


def test_a_presets_file_with_the_wrong_shape_is_refused_with_advice(
    client: TestClient, paths: RuntimePaths
) -> None:
    _presets_file(paths).write_text('{"schema_version": 1, "presets": [1]}', encoding="utf-8")
    response = client.get("/config/presets")
    assert response.status_code == 500
    assert "delete the file" in response.json()["detail"]


def test_an_unreadable_presets_file_still_lists_no_presets(
    client: TestClient, paths: RuntimePaths
) -> None:
    _presets_file(paths).write_text("{oops", encoding="utf-8")
    assert client.get("/config/presets").json()["user"] == {}
