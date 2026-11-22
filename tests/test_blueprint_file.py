"""Blueprint files are versioned: saves stamp them and every reader strips the key."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routes.run as run_routes
import routes.templates as template_routes
from core.boot_strapper import BootStrapper

NEWER_VERSION = 99

with open("templates/wikiMD.json", encoding="utf-8") as _f:
    GOOD = json.load(_f)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, Path]:
    monkeypatch.setattr(template_routes, "TEMPLATES_DIR", str(tmp_path))
    monkeypatch.setattr(run_routes, "TEMPLATES_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(template_routes.router)
    app.include_router(run_routes.router)
    return TestClient(app), tmp_path


def test_a_saved_blueprint_carries_the_schema_version(client: tuple[TestClient, Path]) -> None:
    c, directory = client
    assert c.put("/templates/x", json={"content": GOOD}).status_code == 200
    stored = json.loads((directory / "x.json").read_text(encoding="utf-8"))
    assert stored["schema_version"] == 1
    assert {k: v for k, v in stored.items() if k != "schema_version"} == GOOD


def test_a_created_blueprint_carries_the_schema_version(client: tuple[TestClient, Path]) -> None:
    c, directory = client
    assert c.post("/templates?name=y", json={"content": GOOD}).status_code == 200
    assert json.loads((directory / "y.json").read_text(encoding="utf-8"))["schema_version"] == 1


def test_the_editor_gets_the_blueprint_without_the_version(
    client: tuple[TestClient, Path],
) -> None:
    c, _ = client
    c.put("/templates/x", json={"content": GOOD})
    assert c.get("/templates/x").json() == GOOD


def test_an_unversioned_blueprint_is_read_as_before(client: tuple[TestClient, Path]) -> None:
    c, directory = client
    (directory / "old.json").write_text(json.dumps(GOOD), encoding="utf-8")
    assert c.get("/templates/old").json() == GOOD


def test_a_version_sent_with_the_content_is_not_kept_twice(
    client: tuple[TestClient, Path],
) -> None:
    c, directory = client
    sent = {**GOOD, "schema_version": 1}
    assert c.put("/templates/x", json={"content": sent}).status_code == 200
    stored = json.loads((directory / "x.json").read_text(encoding="utf-8"))
    assert stored["schema_version"] == 1


def test_a_newer_version_sent_by_the_editor_is_refused(client: tuple[TestClient, Path]) -> None:
    c, directory = client
    sent = {**GOOD, "schema_version": NEWER_VERSION}
    response = c.put("/templates/x", json={"content": sent})
    assert response.status_code == 422
    assert "Update CrawlViz" in response.json()["detail"]
    assert not list(directory.iterdir())


def test_a_newer_blueprint_is_refused_by_the_editor_route(client: tuple[TestClient, Path]) -> None:
    c, directory = client
    (directory / "new.json").write_text(
        json.dumps({**GOOD, "schema_version": NEWER_VERSION}), encoding="utf-8"
    )
    response = c.get("/templates/new")
    assert response.status_code == 422
    assert "Update CrawlViz" in response.json()["detail"]


def test_a_newer_blueprint_is_refused_by_run_and_names_the_file(
    client: tuple[TestClient, Path],
) -> None:
    c, directory = client
    (directory / "new.json").write_text(
        json.dumps({**GOOD, "schema_version": NEWER_VERSION}), encoding="utf-8"
    )
    response = c.post("/run", json={"templateName": "new.json"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "new.json" in detail and "Update CrawlViz" in detail


def test_the_crawl_bootstrapper_reads_a_versioned_blueprint(tmp_path: Path) -> None:
    path = tmp_path / "versioned.json"
    path.write_text(json.dumps({**GOOD, "schema_version": 1}), encoding="utf-8")
    bootstrapper = BootStrapper(None, None, "versioned.json", templates_dir=tmp_path)
    template = bootstrapper.load_template()
    assert "schema_version" not in template
    assert template["scoring"] == GOOD["scoring"]
