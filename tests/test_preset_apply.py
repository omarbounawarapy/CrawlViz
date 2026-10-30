"""Applying a preset merges it over the current settings and says what it changed."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routes.config as config_routes
from config import settings_store as store
from config.paths import RuntimePaths
from config.runtime_config import default_runtime_config
from routes import config_support


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, RuntimePaths]:
    paths = RuntimePaths.under(tmp_path)
    monkeypatch.setattr(config_support, "default_runtime_paths", lambda: paths)
    app = FastAPI()
    app.include_router(config_routes.router)
    return TestClient(app), paths


def test_apply_keeps_settings_the_preset_does_not_mention(
    client: tuple[TestClient, RuntimePaths],
) -> None:
    c, paths = client
    c.put("/config", json={"values": {"fetch": {"user_agent": "Mine/1", "min_delay": 4.0}}})
    c.put("/config", json={"values": {"pipelines": {"filtering": {"workers": 5}}}})

    applied = c.post("/config/presets/polite/apply").json()

    assert applied["fetch"]["min_delay"] == 2.0
    assert applied["fetch"]["user_agent"] == "Mine/1"
    assert applied["pipelines"]["filtering"]["workers"] == 5
    assert store.read_stored(paths.settings_file)["fetch"]["user_agent"] == "Mine/1"


def test_apply_reports_each_changed_field_with_old_and_new_value(
    client: tuple[TestClient, RuntimePaths],
) -> None:
    c, _ = client
    c.put("/config", json={"values": {"fetch": {"min_delay": 4.0}}})
    default_jitter = default_runtime_config().fetch.jitter_max

    changes = c.post("/config/presets/polite/apply").json()["changes"]

    assert {"path": "fetch.min_delay", "old": 4.0, "new": 2.0} in changes
    assert {"path": "fetch.jitter_max", "old": default_jitter, "new": 0.5} in changes
    assert all(change["old"] != change["new"] for change in changes)


def test_preview_returns_the_changes_and_saves_nothing(
    client: tuple[TestClient, RuntimePaths],
) -> None:
    c, paths = client
    c.put("/config", json={"values": {"fetch": {"min_delay": 4.0}}})
    stored_before = store.read_stored(paths.settings_file)

    response = c.post("/config/presets/fast/preview")

    assert response.status_code == 200
    assert {"path": "fetch.min_delay", "old": 4.0, "new": 0.2} in response.json()["changes"]
    assert store.read_stored(paths.settings_file) == stored_before


def test_preview_of_a_missing_preset_is_404(client: tuple[TestClient, RuntimePaths]) -> None:
    c, _ = client
    assert c.post("/config/presets/nope/preview").status_code == 404


def test_changed_fields_lists_only_differences_by_dotted_path() -> None:
    old = {"a": {"b": 1, "c": 2}, "d": [1]}
    new = {"a": {"b": 1, "c": 3}, "d": [1, 2]}
    assert store.changed_fields(old, new) == [
        {"path": "a.c", "old": 2, "new": 3},
        {"path": "d", "old": [1], "new": [1, 2]},
    ]
