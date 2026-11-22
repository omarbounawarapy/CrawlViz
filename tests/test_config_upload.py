"""A settings.json copy uploaded to the config routes loads like the stored file does."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routes.config as config_routes
from config import settings_store as store
from config.paths import RuntimePaths
from routes import config_support

# A file written before the pipeline sections were renamed (`requests` is now `fetch`).
OLD_FORMAT_UPLOAD = {"schema_version": 1, "pipelines": {"requests": {"workers": 3}}}
NEWER_FORMAT_UPLOAD = {"schema_version": 99, "fetch": {"min_delay": 4.0}}


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


def test_validate_accepts_an_old_format_settings_file(client: TestClient) -> None:
    result = client.post("/config/validate", json={"values": OLD_FORMAT_UPLOAD}).json()
    assert result == {"valid": True, "errors": []}


def test_validate_accepts_a_current_settings_file_with_its_version(client: TestClient) -> None:
    upload = {"schema_version": 2, "pipelines": {"fetch": {"workers": 3}}}
    assert client.post("/config/validate", json={"values": upload}).json()["valid"] is True


def test_replace_stores_an_old_format_settings_file_under_the_current_names(
    client: TestClient, paths: RuntimePaths
) -> None:
    response = client.put("/config/replace", json={"values": OLD_FORMAT_UPLOAD})
    assert response.status_code == 200
    assert response.json()["pipelines"]["fetch"]["workers"] == 3
    written = json.loads(paths.settings_file.read_text(encoding="utf-8"))
    assert written["pipelines"] == {"fetch": {"workers": 3}}
    assert written["schema_version"] == 2


def test_a_file_from_a_newer_crawlviz_is_refused_with_both_versions_named(
    client: TestClient, paths: RuntimePaths
) -> None:
    result = client.post("/config/validate", json={"values": NEWER_FORMAT_UPLOAD}).json()
    assert result["valid"] is False
    (problem,) = result["errors"]
    assert problem["path"] == "schema_version"
    assert "99" in problem["message"] and "Update CrawlViz" in problem["message"]

    response = client.put("/config/replace", json={"values": NEWER_FORMAT_UPLOAD})
    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["path"] == "schema_version"
    assert not paths.settings_file.exists()


def test_a_section_given_under_both_names_is_refused_not_guessed(client: TestClient) -> None:
    upload = {"pipelines": {"requests": {"workers": 2}, "fetch": {"workers": 4}}}
    result = client.post("/config/validate", json={"values": upload}).json()
    assert result["valid"] is False and result["errors"][0]["path"] == "pipelines"


def test_an_unknown_key_in_a_versioned_upload_is_still_named(client: TestClient) -> None:
    upload = {"schema_version": 2, "bogus": 1}
    result = client.post("/config/validate", json={"values": upload}).json()
    assert [problem["path"] for problem in result["errors"]] == ["bogus"]


def test_the_loader_does_not_change_the_uploaded_values() -> None:
    upload = {"schema_version": 1, "pipelines": {"requests": {"workers": 3}}}
    store.load_uploaded_settings(upload)
    assert upload == {"schema_version": 1, "pipelines": {"requests": {"workers": 3}}}
