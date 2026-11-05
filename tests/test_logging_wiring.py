"""Logging is set up where the app and a crawl start (OBS-1), and keys never reach it (SEC-3)."""

import asyncio
import importlib
import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from config.paths import KEYS_FILE_NAME, RuntimePaths
from core import Crawler
from core.boot_strapper import BootStrapper
from infrastructure.key_manager import KeyManager
from routes import config_support
from routes.session_token import get_session_token
from traceability.logging_setup import JsonLineFormatter, get_log_ids
from utils.log_redaction import REDACTED, clear_registered_secrets, redact_secrets

API_KEY = "gsk_ThisIsAFakeKeyForTests1234567890"


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    clear_registered_secrets()
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    clear_registered_secrets()


def formatted(message: str) -> str:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, message, None, None)
    return JsonLineFormatter().format(record)


def test_a_crawl_binds_its_id_for_the_whole_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    crawler = Crawler("topic.json", paths=RuntimePaths.under(tmp_path))
    seen: list[dict[str, str]] = []

    async def bootstrap(self: BootStrapper) -> dict[str, str]:
        seen.append(get_log_ids())
        return {}

    async def run_session(self: Crawler, blueprint: dict[str, str]) -> None:
        # The stages run as tasks created here, which inherit the crawl's context.
        seen.append(await asyncio.create_task(asyncio.sleep(0, get_log_ids())))

    monkeypatch.setattr(BootStrapper, "bootstrap", bootstrap)
    monkeypatch.setattr(Crawler, "_run_session", run_session)
    asyncio.run(crawler.start())
    assert seen == [{"crawl_id": crawler.crawl_id}] * 2
    assert get_log_ids() == {}


def test_a_crawl_registers_the_keys_it_uses(tmp_path: Path) -> None:
    keys_path = tmp_path / KEYS_FILE_NAME
    keys_path.write_text(json.dumps({"groq": [API_KEY]}), encoding="utf-8")
    crawler = Crawler(
        "topic.json",
        paths=RuntimePaths.under(tmp_path),
        key_manager=KeyManager(keys_file=keys_path),
    )
    crawler._setup_traceability()
    assert API_KEY not in formatted(f"calling with {API_KEY}")


def test_adding_a_key_through_the_api_registers_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = RuntimePaths.under(tmp_path)
    monkeypatch.setattr(config_support, "default_runtime_paths", lambda: paths)
    client = TestClient(main.app, base_url="http://localhost:8000")
    token = client.get("/session").json()["token"]
    reply = client.post(
        "/keys",
        json={"provider": "groq", "key": API_KEY},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reply.status_code == 200
    assert redact_secrets(f"retry with {API_KEY}") == f"retry with {REDACTED}"


def test_the_app_redacts_its_session_token_and_logs_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    importlib.reload(main)
    assert redact_secrets(f"sent {get_session_token()}") == f"sent {REDACTED}"
    logging.getLogger("uvicorn.error").info("up")
    assert json.loads(capsys.readouterr().err.splitlines()[-1])["message"] == "up"
