"""Offline mode: a full crawl with no keys and no network."""

import asyncio
import json
import socket
from pathlib import Path

import pytest

from config.paths import RuntimePaths
from config.runtime_config import default_runtime_config
from core import Crawler
from offline import OFFLINE_ENV_VAR, build_offline_session, is_offline

EXPECTED_EMBEDDING_BACKEND = "hashing"
CRAWL_TIMEOUT_SECONDS = 120


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.parametrize("value", ["1", "true", "TRUE", " yes ", "on"])
def test_offline_variable_turns_offline_mode_on(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(OFFLINE_ENV_VAR, value)
    assert is_offline()


@pytest.mark.parametrize("value", [None, "", "0", "false", "off"])
def test_offline_mode_is_off_unless_asked_for(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(OFFLINE_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(OFFLINE_ENV_VAR, value)
    assert not is_offline()


def test_session_switches_the_config_to_hashing_embeddings() -> None:
    session = build_offline_session(default_runtime_config())
    assert session.config.embeddings.backend == EXPECTED_EMBEDDING_BACKEND


@pytest.mark.slow
async def test_offline_crawl_runs_to_its_stop_condition_without_keys(tmp_path: Path) -> None:
    session = build_offline_session(default_runtime_config())
    paths = RuntimePaths.under(tmp_path)  # no keys.json in it
    crawler = Crawler(
        "offline_demo.json",
        config=session.config,
        paths=paths,
        seed=0,
        ui_port=_free_port(),
        llm=session.llm,
        fetcher=session.fetcher,
    )

    await asyncio.wait_for(crawler.start(), CRAWL_TIMEOUT_SECONDS)

    blueprint = json.loads((paths.templates_dir / "offline_demo.json").read_text())
    max_nodes = blueprint["stop_conditions"]["max_nodes"]
    in_flight = session.config.pipelines.requests.workers  # fetches already started at the stop
    assert 1 < len(session.fetcher.fetched) <= max_nodes + in_flight
    assert not paths.keys_file.exists()
