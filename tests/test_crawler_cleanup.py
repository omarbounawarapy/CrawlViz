"""When a crawl fails while its stages are being built, every HTTP client and session
created so far is closed, so nothing leaks from a run that never started."""

import socket
from pathlib import Path
from typing import Any

import pytest

import core.stages
from config.paths import RuntimePaths
from config.runtime_config import default_runtime_config
from core.crawler import Crawler
from core.stages import STAGES, StageInputs, StageSpec
from infrastructure import KeyManager, NetworkClient
from nlp import BufferManager, SpaceUpdater
from tests.test_event_wiring import FAKE_BLUEPRINT, Fake
from ui_bridge.event_recorder import EventRecorder

FLUSH_INTERVAL_SECONDS = 3600
LLM_URL = "http://llm.invalid/v1"


class StageBuildError(RuntimeError):
    pass


class _Session:
    """Stands in for an open aiohttp session."""

    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _HttpSpy:
    """Records every NetworkClient the crawl creates and every session one opens.

    The real client opens its session on first use; here the first request opens a fake."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.clients: list[NetworkClient] = []
        self.sessions: list[_Session] = []
        real_init = NetworkClient.__init__
        real_close = NetworkClient.close
        spy = self

        def init(client: NetworkClient, *args: Any, **kwargs: Any) -> None:
            real_init(client, *args, **kwargs)
            spy.clients.append(client)

        async def emit_request(client: NetworkClient, params: dict[str, Any]) -> str:
            if client.session is None:
                session = _Session()
                spy.sessions.append(session)
                client.session = session  # type: ignore[assignment]
            return ""

        async def close(client: NetworkClient) -> None:
            await real_close(client)
            client.closed = True  # type: ignore[attr-defined]

        monkeypatch.setattr(NetworkClient, "__init__", init)
        monkeypatch.setattr(NetworkClient, "emit_request", emit_request)
        monkeypatch.setattr(NetworkClient, "close", close)

    def unclosed_clients(self) -> list[NetworkClient]:
        return [client for client in self.clients if not getattr(client, "closed", False)]

    def open_sessions(self) -> list[_Session]:
        return [session for session in self.sessions if not session.closed]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _crawler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Crawler:
    """A crawl with no injected LLM or fetcher, so it creates real HTTP clients."""
    keystore = tmp_path / "keystore.json"
    keystore.write_text("{}", encoding="utf-8")  # no provider keys: the LLM is never called
    crawler = Crawler(
        "wikiMD.json",
        config=default_runtime_config(),
        paths=RuntimePaths.under(tmp_path),
        ui_port=_free_port(),
        key_manager=KeyManager(keys_file=keystore),
    )
    traced: dict[str, Any] = {}
    real_setup = crawler._setup_traceability

    def setup_traceability() -> Any:
        result = real_setup()
        traced["network"] = result[1]
        return result

    async def build_nlp(traced_llm: object, tracer: object) -> tuple[Fake, SpaceUpdater, Fake]:
        # The expansion call goes out through the traced client: it opens its session.
        await traced["network"].emit_request({"url": LLM_URL})
        return (
            Fake(),
            SpaceUpdater(Fake(), BufferManager(), flush_interval=FLUSH_INTERVAL_SECONDS),
            Fake(),
        )

    monkeypatch.setattr(crawler, "_setup_traceability", setup_traceability)
    monkeypatch.setattr(crawler, "_build_nlp_subsystem", build_nlp)
    return crawler


def _fail_last_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every stage but the last builds; the last one raises."""

    def build_stopping(inputs: StageInputs, built: core.stages.Built) -> Any:
        raise StageBuildError("the stopping stage could not be built")

    last = STAGES[-1]
    monkeypatch.setattr(
        core.stages, "STAGES", (*STAGES[:-1], StageSpec(last.key, None, build_stopping))
    )


async def test_failed_stage_build_closes_every_http_client_and_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _HttpSpy(monkeypatch)
    crawler = _crawler(tmp_path, monkeypatch)
    _fail_last_stage(monkeypatch)

    with pytest.raises(StageBuildError):
        await crawler._run_session(FAKE_BLUEPRINT)

    assert spy.sessions, "the LLM client should have opened a session before the failure"
    assert spy.open_sessions() == []
    assert spy.unclosed_clients() == []


async def test_failed_ui_layer_build_closes_the_event_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    crawler = Crawler(
        "wikiMD.json",
        config=default_runtime_config(),
        paths=RuntimePaths.under(tmp_path),
        ui_port=_free_port(),
    )
    crawler._load_blueprint_config(FAKE_BLUEPRINT)
    inert: Any = Fake()  # no builder calls the services
    pipelines = crawler._build_pipelines(FAKE_BLUEPRINT, inert, inert)
    recorders: list[EventRecorder] = []
    real_init = EventRecorder.__init__
    closed: list[EventRecorder] = []
    real_close = EventRecorder.close

    def init(recorder: EventRecorder, run_dir: Path) -> None:
        real_init(recorder, run_dir)
        recorders.append(recorder)

    def close(recorder: EventRecorder) -> None:
        closed.append(recorder)
        real_close(recorder)

    def write_manifest(recorder: EventRecorder, manifest: dict[str, Any]) -> None:
        raise StageBuildError("the manifest could not be written")

    monkeypatch.setattr(EventRecorder, "__init__", init)
    monkeypatch.setattr(EventRecorder, "close", close)
    monkeypatch.setattr(EventRecorder, "write_manifest", write_manifest)

    with pytest.raises(StageBuildError):
        crawler._build_ui_layer(pipelines)

    assert recorders and closed == recorders
