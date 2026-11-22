"""A damaged settings.json is reported, never replaced by the defaults without a word."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routes.config as config_routes
from config import settings_store as store
from config.paths import RuntimePaths
from routes import config_support


@pytest.fixture
def damaged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, RuntimePaths]:
    paths = RuntimePaths.under(tmp_path)
    monkeypatch.setattr(config_support, "default_runtime_paths", lambda: paths)
    paths.settings_file.parent.mkdir(parents=True, exist_ok=True)
    paths.settings_file.write_text('{"fetch": {"min_delay": ', encoding="utf-8")
    app = FastAPI()
    app.include_router(config_routes.router)
    return TestClient(app), paths


def test_missing_settings_file_means_no_stored_settings(tmp_path: Path) -> None:
    assert store.read_stored(tmp_path / "settings.json") == {}


def test_invalid_json_raises_a_plain_words_error(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(store.SettingsFileError, match="not valid JSON"):
        store.read_stored(path)


def test_a_json_list_is_not_a_settings_object(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(store.SettingsFileError, match="JSON object"):
        store.load_runtime_config(path)


def test_saving_over_a_damaged_file_does_not_overwrite_it(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(store.SettingsFileError):
        store.save_settings(path, {"fetch": {"min_delay": 3.0}})
    assert path.read_text(encoding="utf-8") == "{oops"


def test_full_reset_repairs_a_damaged_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{oops", encoding="utf-8")
    store.reset_settings(path)
    assert store.read_stored(path) == {}


def test_config_route_says_what_is_wrong_and_what_to_do(
    damaged: tuple[TestClient, RuntimePaths],
) -> None:
    client, paths = damaged
    response = client.get("/config")
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert str(paths.settings_file) in detail and "reset the settings" in detail


def test_reset_route_works_on_a_damaged_file(damaged: tuple[TestClient, RuntimePaths]) -> None:
    client, _ = damaged
    assert client.post("/config/reset").status_code == 200
    assert client.get("/config").status_code == 200
