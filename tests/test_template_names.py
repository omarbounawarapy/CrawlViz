"""Blueprint names and crawl ids are plain: no path can leave the templates directory."""

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.template_names import (
    InvalidTemplateNameError,
    resolve_template_path,
    validate_template_name,
)
from core import Crawler
from routes import run as run_routes
from routes import templates as template_routes

CRAWL_ID = re.compile(r"[A-Za-z0-9_-]+")
HOSTILE_NAMES = [
    "../README.md",
    "../templates/isi.json",
    "..\\secret.json",
    "/etc/passwd",
    "sub/isi.json",
    ".hidden.json",
    "isi.json\x00.txt",
    "isi",
    "isi.json ",
    "",
    "a" * 200 + ".json",
]


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(template_routes, "TEMPLATES_DIR", str(tmp_path))
    monkeypatch.setattr(run_routes, "TEMPLATES_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(template_routes.router)
    app.include_router(run_routes.router)
    return TestClient(app)


@pytest.mark.parametrize(
    "name", ["isi.json", "wikiMD.json", "offline_demo.json", "my blueprint.v2.json"]
)
def test_plain_names_are_accepted(name: str, tmp_path: Path) -> None:
    assert validate_template_name(name) == name
    assert resolve_template_path(tmp_path, name) == tmp_path / name


@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_hostile_names_are_refused(name: str, tmp_path: Path) -> None:
    with pytest.raises(InvalidTemplateNameError):
        resolve_template_path(tmp_path, name)


@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_run_refuses_a_hostile_template_name(client: TestClient, name: str) -> None:
    assert client.post("/run", json={"templateName": name}).status_code == 422


def test_run_does_not_reach_files_outside_the_templates_directory(
    client: TestClient, tmp_path: Path
) -> None:
    (tmp_path.parent / "outside.json").write_text("{}")
    response = client.post("/run", json={"templateName": f"../{tmp_path.parent.name}/outside.json"})
    assert response.status_code == 422


def test_template_routes_refuse_hostile_names(client: TestClient) -> None:
    assert client.post("/templates?name=../evil", json={"content": {}}).status_code == 422
    assert client.put("/templates/..%5Cevil", json={"content": {}}).status_code == 422
    assert client.get("/templates/.hidden").status_code == 422


def test_crawler_refuses_a_hostile_template_name() -> None:
    with pytest.raises(InvalidTemplateNameError):
        Crawler("../../etc/passwd.json")


def test_crawl_id_uses_only_safe_characters() -> None:
    assert CRAWL_ID.fullmatch(Crawler("my blueprint.v2.json").crawl_id)


def test_crawl_id_keeps_the_blueprint_stem_and_a_timestamp() -> None:
    crawl_id = Crawler("wikiMD.json").crawl_id
    assert re.fullmatch(r"wikiMD-\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}", crawl_id)
