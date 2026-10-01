import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routes.run as run_routes
import routes.templates as template_routes
from core.boot_strapper import BootStrapper
from routes.blueprint_schema import BlueprintSchemaError, validate_blueprint

with open("templates/wikiMD.json", encoding="utf-8") as _f:
    GOOD = json.load(_f)


def _bad():
    bad = json.loads(json.dumps(GOOD))
    del bad["scoring"]
    return bad


def test_validate_blueprint_reports_path():
    with pytest.raises(BlueprintSchemaError, match="scoring"):
        validate_blueprint(_bad())


def test_bootstrapper_rejects_malformed_template(tmp_path):
    (tmp_path / "bad.json").write_text(json.dumps(_bad()))
    bs = BootStrapper(None, None, "bad.json")
    bs.template_file = tmp_path / "bad.json"
    with pytest.raises(BlueprintSchemaError):
        bs.load_template()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(template_routes, "TEMPLATES_DIR", str(tmp_path))
    monkeypatch.setattr(run_routes, "TEMPLATES_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(template_routes.router)
    app.include_router(run_routes.router)
    return TestClient(app), tmp_path


def test_run_returns_422_for_malformed_template(client):
    c, d = client
    (d / "bad.json").write_text(json.dumps(_bad()))
    r = c.post("/run", json={"templateName": "bad.json"})
    assert r.status_code == 422 and "scoring" in r.json()["detail"]


def test_put_and_post_validate(client):
    c, d = client
    assert c.put("/templates/x", json={"content": _bad()}).status_code == 422
    assert c.post("/templates?name=y", json={"content": _bad()}).status_code == 422
    assert not list(d.iterdir())
    assert c.put("/templates/x", json={"content": GOOD}).status_code == 200
