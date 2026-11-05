"""`/keys`: the keys file is created owner-only, and no reply carries a submitted key."""

import os
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from config.paths import RuntimePaths
from crawlviz.llm.key_manager import KEYS_FILE_MODE
from routes import config_support
from routes.session_token import get_session_token

FAKE_SECRET = "gsk_ThisIsAFakeKeyForTests1234567890"


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


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_listing_keys_creates_a_missing_keys_file_owner_only(
    client: TestClient, headers: dict[str, str], paths: RuntimePaths
) -> None:
    old_umask = os.umask(0)
    try:
        reply = client.get("/keys", headers=headers)
    finally:
        os.umask(old_umask)
    assert reply.status_code == 200
    assert reply.json() == {}
    assert stat.S_IMODE(paths.keys_file.stat().st_mode) == KEYS_FILE_MODE


@pytest.mark.parametrize(
    "body",
    [{"key": FAKE_SECRET}, {"provider": 7, "key": FAKE_SECRET}, {"provider": "groq", "key": 12}],
    ids=["missing provider", "mistyped provider", "mistyped key"],
)
def test_a_rejected_key_body_is_not_echoed_back(
    client: TestClient, headers: dict[str, str], paths: RuntimePaths, body: dict[str, object]
) -> None:
    reply = client.post("/keys", json=body, headers=headers)
    assert reply.status_code == 422
    assert FAKE_SECRET not in reply.text
    for problem in reply.json()["detail"]:
        assert set(problem) == {"type", "loc", "msg"}


def test_a_validation_reply_keeps_where_and_why(
    client: TestClient, headers: dict[str, str], paths: RuntimePaths
) -> None:
    reply = client.post("/keys", json={"key": FAKE_SECRET}, headers=headers)
    assert reply.json()["detail"] == [
        {"type": "missing", "loc": ["body", "provider"], "msg": "Field required"}
    ]


def test_the_guards_still_run_before_validation(client: TestClient) -> None:
    body = {"key": FAKE_SECRET}
    token = {"Authorization": f"Bearer {get_session_token()}"}
    assert client.post("/keys", json=body).status_code == 401
    assert (
        client.post("/keys", json=body, headers={**token, "Host": "evil.example"}).status_code
        == 421
    )
    foreign_origin = client.post(
        "/keys", json=body, headers={**token, "Origin": "https://evil.example"}
    )
    assert foreign_origin.status_code == 403
    assert client.post("/keys", content="x", headers=token).status_code == 415
