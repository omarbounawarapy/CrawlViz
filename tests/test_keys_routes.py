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
