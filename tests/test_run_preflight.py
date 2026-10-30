"""POST /run answers a missing key, a bad blueprint or a busy port in plain words, before any
work."""

import json
import socket
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import LLM_DEFAULT_ENDPOINTS
from config.paths import RuntimePaths
from config.runtime_config import default_runtime_config
from core import find_preflight_problems
from routes import run as run_routes

PROVIDER = "groq"
DUMMY_KEY = "dummy-key-for-tests-0000"


@pytest.fixture
def free_port():
    with socket.socket() as probe:
        probe.bind(("localhost", 0))
        return probe.getsockname()[1]


@pytest.fixture
def config(free_port):
    config = default_runtime_config()
    config.observability.ui_port = free_port
    return config


def test_no_problems_when_a_key_is_saved_and_the_port_is_free(tmp_path: Path, config) -> None:
    keys = tmp_path / "keys.json"
    keys.write_text(json.dumps({PROVIDER: [DUMMY_KEY]}), encoding="utf-8")
    assert find_preflight_problems(PROVIDER, config, keys, offline=False) == []


def test_missing_keys_file_says_which_key_to_add(tmp_path: Path, config) -> None:
    problems = find_preflight_problems(PROVIDER, config, tmp_path / "keys.json", offline=False)
    assert len(problems) == 1
    assert f"no {PROVIDER} API key is saved" in problems[0] and "Configuration page" in problems[0]


def test_unreadable_keys_file_says_so_without_echoing_keys(tmp_path: Path, config) -> None:
    keys = tmp_path / "keys.json"
    keys.write_text(json.dumps({PROVIDER: DUMMY_KEY}), encoding="utf-8")
    (problem,) = find_preflight_problems(PROVIDER, config, keys, offline=False)
    assert "could not be read" in problem and DUMMY_KEY not in problem


def test_a_provider_pointed_at_your_own_server_needs_no_key(tmp_path: Path, config) -> None:
    config.providers.endpoints[PROVIDER] = "http://localhost:11434/v1/chat/completions"
    assert find_preflight_problems(PROVIDER, config, tmp_path / "keys.json", offline=False) == []


def test_an_unknown_provider_lists_the_supported_ones(tmp_path: Path, config) -> None:
    (problem,) = find_preflight_problems("nope", config, tmp_path / "keys.json", offline=False)
    assert "'nope'" in problem and all(name in problem for name in LLM_DEFAULT_ENDPOINTS)


def test_offline_crawls_need_no_key(tmp_path: Path, config) -> None:
    assert find_preflight_problems(PROVIDER, config, tmp_path / "keys.json", offline=True) == []


def test_a_busy_port_is_reported_with_what_to_do(tmp_path: Path, config) -> None:
    with socket.socket() as holder:
        holder.bind(("localhost", 0))
        holder.listen()
        config.observability.ui_port = holder.getsockname()[1]
        problems = find_preflight_problems(PROVIDER, config, tmp_path / "keys.json", offline=True)
    assert len(problems) == 1
    assert "already in use" in problems[0] and "Observability" in problems[0]


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    paths = RuntimePaths.under(tmp_path)
    started = []

    async def fake_run(template_name, config=None, seed=None):
        started.append(template_name)

    monkeypatch.setattr(run_routes, "default_runtime_paths", lambda: paths)
    monkeypatch.setattr(run_routes, "is_offline", lambda: False)
    monkeypatch.setattr(run_routes, "_run_crawler", fake_run)
    monkeypatch.setattr(run_routes, "_current_task", None)
    app = FastAPI()
    app.include_router(run_routes.router)
    return TestClient(app), paths, started


def test_run_without_a_key_is_refused_before_the_crawl_starts(client) -> None:
    c, _, started = client
    response = c.post("/run", json={"templateName": "wikiMD.json"})
    assert response.status_code == 409
    assert "API key" in response.json()["detail"]
    assert started == [] and run_routes._current_task is None


def test_run_with_a_key_starts(client, free_port) -> None:
    c, paths, _ = client
    paths.keys_file.write_text(json.dumps({PROVIDER: [DUMMY_KEY]}), encoding="utf-8")
    overrides = {"observability": {"ui_port": free_port}}
    response = c.post("/run", json={"templateName": "wikiMD.json", "overrides": overrides})
    assert response.status_code == 200 and response.json() == {"started": "wikiMD.json"}


def test_run_with_a_damaged_settings_file_says_how_to_repair_it(client) -> None:
    c, paths, _ = client
    paths.settings_file.write_text("{oops", encoding="utf-8")
    response = c.post("/run", json={"templateName": "wikiMD.json"})
    assert response.status_code == 500
    assert "reset the settings" in response.json()["detail"]


def test_run_with_a_broken_blueprint_names_the_file_and_the_fix(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, _, _ = client
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(run_routes, "TEMPLATES_DIR", str(tmp_path))
    response = c.post("/run", json={"templateName": "broken.json"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "broken.json" in detail and "not valid JSON" in detail and "Blueprints page" in detail
