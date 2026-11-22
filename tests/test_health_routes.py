"""`GET /health` and `GET /ready`: liveness and readiness, behind the same guards as every route."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from config.paths import RuntimePaths
from crawlviz.api import schemas
from routes import config_support, health
from routes.session_token import get_session_token

SKIP_WHEN_ROOT = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root can write anywhere"
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app, base_url="http://localhost:8000")


@pytest.fixture
def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_session_token()}"}


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RuntimePaths]:
    runtime_paths = RuntimePaths.under(tmp_path / "data")
    monkeypatch.setattr(config_support, "default_runtime_paths", lambda: runtime_paths)
    yield runtime_paths


def test_health_reports_the_process_is_up(client: TestClient, headers: dict[str, str]) -> None:
    reply = client.get("/health", headers=headers)
    assert reply.status_code == 200
    assert reply.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/health", "/ready"])
def test_the_probes_need_the_session_token(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401


@pytest.mark.parametrize("path", ["/health", "/ready"])
def test_the_probes_refuse_a_foreign_host_or_origin(
    client: TestClient, headers: dict[str, str], path: str
) -> None:
    assert client.get(path, headers={**headers, "Host": "evil.example"}).status_code == 421
    assert (
        client.get(path, headers={**headers, "Origin": "https://evil.example"}).status_code == 403
    )


def test_ready_when_settings_load_and_folders_can_be_written(
    client: TestClient, headers: dict[str, str], paths: RuntimePaths
) -> None:
    reply = client.get("/ready", headers=headers)
    assert reply.status_code == 200
    body = reply.json()
    assert body["ready"] is True
    assert {check["name"] for check in body["checks"]} >= {"settings", "export_dir", "log_dir"}
    assert all(check["ok"] and check["detail"] is None for check in body["checks"])


def test_ready_creates_nothing(
    client: TestClient, headers: dict[str, str], paths: RuntimePaths
) -> None:
    client.get("/ready", headers=headers)
    assert not paths.export_dir.exists()
    assert not paths.log_dir.exists()


def test_a_damaged_settings_file_makes_the_app_not_ready(
    client: TestClient, headers: dict[str, str], paths: RuntimePaths
) -> None:
    paths.settings_file.parent.mkdir(parents=True)
    paths.settings_file.write_text("{oops", encoding="utf-8")
    reply = client.get("/ready", headers=headers)
    assert reply.status_code == 503
    body = reply.json()
    assert body["ready"] is False
    failed = [check for check in body["checks"] if not check["ok"]]
    assert [check["name"] for check in failed] == ["settings"]
    assert "not valid JSON" in failed[0]["detail"]


@SKIP_WHEN_ROOT
def test_a_folder_that_cannot_be_written_is_named(
    client: TestClient, headers: dict[str, str], paths: RuntimePaths
) -> None:
    paths.export_dir.parent.mkdir(parents=True)
    paths.export_dir.mkdir()
    paths.export_dir.chmod(0o500)
    try:
        reply = client.get("/ready", headers=headers)
    finally:
        paths.export_dir.chmod(0o700)
    assert reply.status_code == 503
    failed = [check for check in reply.json()["checks"] if not check["ok"]]
    assert [check["name"] for check in failed] == ["export_dir"]
    assert str(paths.export_dir) in failed[0]["detail"]


def test_the_replies_come_from_the_api_schemas_not_a_copy() -> None:
    declared = {route.path: route.response_model for route in health.router.routes}  # type: ignore[attr-defined]

    assert declared == {"/health": schemas.HealthReply, "/ready": schemas.ReadyReply}
