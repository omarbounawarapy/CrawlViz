"""Composition root for a single crawl session.

``Crawler.start()`` reads a blueprint (see ``core.boot_strapper``),
builds the 13 pipelines from the registry in ``core.stages`` (plus the
space updater and the telemetry bridge and gateway) described in the
project report's architecture chapters, wires them together through one
:class:`~core.event_broker.EventBroker`, and runs them concurrently
until a stop condition fires and every pipeline has drained (see
``pipelines.stopping_pipeline``), or until the task is cancelled from
outside (the manual STOP endpoint in ``routes.run``).
"""

import asyncio
import logging
from contextlib import AsyncExitStack
from datetime import datetime

from config.paths import RuntimePaths, default_runtime_paths
from config.runtime_config import RuntimeConfig, default_runtime_config
from config.template_names import template_stem
from utils.html_utils import configure_url_normalization
from infrastructure import KeyManager, LlmHandler, NetworkClient
from infrastructure.call_budget import CallBudget
from models import Storage
from nlp import BufferManager, SpaceUpdater
from pipelines.contracts import Fetcher, LlmSender
from services import NLPService, ScoringService
from ui_bridge import CrawlStateSnapshot, KeepAlive, TelemetryBridge, UIWebSocketGateway
from ui_bridge.event_recorder import EventRecorder, RecordingGateway, git_sha

from .boot_strapper import BootStrapper
from .event_broker import EventBroker
from .manifest_redaction import redact_manifest
from .stages import STAGES, StageInputs, build_page_fetcher, build_stages, priority_strategy_name

# Traceability is a second, finer-grained event stream (see
# traceability/emitter.py) plus thin wrappers around the network/LLM
# clients that emit it -- this is what produces the granular
# "[NLP] SCORE_EMITTED" / "[LLM] DISPATCHED" trace log lines.
from traceability.emitter import TraceEmitter
from traceability.traced_llm_handler import TracedLlmHandler
from traceability.traced_network_client import TracedNetworkClient

logger = logging.getLogger(__name__)

# Crawl ids name directories under logs, debug and export, so they use only
# letters, digits, hyphens and underscores (no colons).
CRAWL_ID_TIME_FORMAT = "%Y-%m-%d_%H-%M-%S"


class Crawler:
    """Builds and runs one crawl session end to end.

    A Crawler is single-use: construct it with a blueprint filename,
    then ``await crawler.start()``.
    """

    def __init__(
        self,
        template_file: str,
        config: RuntimeConfig | None = None,
        paths: RuntimePaths | None = None,
        key_manager: KeyManager | None = None,
        seed: int | None = None,
        fetch_concurrency: int | None = None,
        scoring_concurrency: int | None = None,
        ui_port: int | None = None,
        llm: LlmSender | None = None,
        fetcher: Fetcher | None = None,
    ):
        self.config = config if config is not None else default_runtime_config()
        configure_url_normalization(
            self.config.url.strip_fragment, self.config.url.strip_trailing_slash
        )
        # Explicit arguments win over the config, which wins over defaults.
        self.ui_port = ui_port if ui_port is not None else self.config.observability.ui_port
        self.seed = seed if seed is not None else self.config.run.seed
        self.fetch_concurrency = (
            fetch_concurrency
            if fetch_concurrency is not None
            else self.config.pipelines.requests.workers
        )
        self.scoring_concurrency = (
            scoring_concurrency
            if scoring_concurrency is not None
            else self.config.pipelines.scoring.workers
        )
        self.paths = paths if paths is not None else default_runtime_paths()
        self.storage = Storage()
        self.template_file = template_file
        self.event_broker = EventBroker()
        # Built lazily in _setup_traceability so constructing a Crawler
        # does not need keys.json.
        self.key_manager = key_manager
        # Replace the LLM provider and the HTTP client, for offline runs
        # (see the offline package). Without them the crawl needs keys and network.
        self.llm = llm
        self.fetcher = fetcher
        started_at = datetime.now().strftime(CRAWL_ID_TIME_FORMAT)
        self.crawl_id = f"{template_stem(template_file)}-{started_at}"

    async def start(self) -> None:
        blueprint = await BootStrapper(
            self.event_broker,
            self.storage,
            self.template_file,
            templates_dir=self.paths.templates_dir,
        ).bootstrap()
        await self._run_session(blueprint)

    async def _run_session(self, blueprint: dict) -> None:
        """Build the stages for `blueprint` and run them until the crawl ends.

        Whatever ends it -- a stop condition, a failure, a cancelled task --
        every resource built on the way is released, in reverse order: the HTTP
        sessions, the UI gateway (its port) and event log, and the vectors still
        buffered for the semantic space. A step that fails does not skip the
        steps after it."""
        async with AsyncExitStack() as cleanup:
            self._load_blueprint_config(blueprint)
            tracer, traced_network, traced_llm = self._setup_traceability()
            if traced_network is not None:
                cleanup.push_async_callback(traced_network.close)

            # Built here, not by the requests stage, so it is closed even when a later
            # stage fails to build.
            fetcher = (
                self.fetcher if self.fetcher is not None else build_page_fetcher(self.config.fetch)
            )
            cleanup.push_async_callback(fetcher.close)

            nlp_service, space_updater, scoring_service = await self._build_nlp_subsystem(
                traced_llm, tracer
            )
            cleanup.push_async_callback(space_updater.force_flush)

            pipelines = self._build_pipelines(
                blueprint, nlp_service, scoring_service, fetcher=fetcher
            )
            self._wire_subscriptions(pipelines, space_updater)
            ui_gateway = self._build_ui_layer(pipelines)
            cleanup.push_async_callback(ui_gateway.stop)

            tasks = self._collect_tasks(pipelines, space_updater, ui_gateway)
            await self._run_until_stopped(tasks, grace=self.config.run.shutdown_grace)

    async def request_stop(self) -> bool:
        """Ask a running crawl to stop the way a stop condition does, so every
        stage drains and flushes. False when the stages are not built yet."""
        stopping = getattr(self, "_pipelines", {}).get("stopping")
        if stopping is None:
            return False
        await stopping.stop_on_request()
        return True

    def queue_depths(self) -> dict:
        """Items waiting in each stage's queue right now, keyed by the Pipelines setting name."""
        pipelines = getattr(self, "_pipelines", None) or {}
        out = {}
        for spec in STAGES:
            queue = getattr(pipelines.get(spec.key), "queue", None)
            if spec.setting is None or queue is None:
                continue
            out[spec.setting] = {"size": queue.qsize(), "max": queue.maxsize or None}
        return out

    def apply_live(self, patch: dict) -> RuntimeConfig:
        """Change live-flagged settings of the running crawl (see
        core/live_settings.py)."""
        from core.live_settings import apply_live

        self.config = apply_live(self.config, getattr(self, "_pipelines", {}), patch)
        return self.config

    async def _run_until_stopped(self, tasks: list, grace: float = 5.0) -> None:
        """Run every task; once the first one finishes (the broker, on
        StopCrawlEvent) give the rest `grace` seconds, then cancel any
        straggler so one hung task cannot keep the crawl "running".
        A task that raises propagates after the others are cancelled."""
        running = [asyncio.ensure_future(t) for t in tasks]
        try:
            done, pending = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            if pending and not any(d.exception() for d in done if not d.cancelled()):
                done2, pending = await asyncio.wait(pending, timeout=grace)
                done |= done2
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for d in done:
                if not d.cancelled() and d.exception():
                    raise d.exception()
        finally:
            # Await the cancelled tasks: their own `finally` blocks (the export
            # flush, closing the log files) only run once they get the cancel.
            for t in running:
                t.cancel()
            await asyncio.gather(*running, return_exceptions=True)

    # =========================================================
    # COMPOSITION STEPS
    # =========================================================
    # The stages themselves come from the registry in core/stages.py
    # (docs/adr/0002-crawl-composition-root.md).

    def _load_blueprint_config(self, blueprint: dict) -> None:
        """Unpack the parts of the blueprint the crawler itself reads; the
        stages read theirs from `StageInputs` (core/stages.py).
        """
        self.blueprint = blueprint
        self.blueprint_id = blueprint.get("blueprint_id")

        self.scoring_config = blueprint.get("scoring")
        self.scoring_strategy = self.scoring_config.get("strategy")
        self.scoring_params = self.scoring_config.get("params")
        self.scoring_type = self.scoring_params.get("scoring_type")
        self.model_information = self.scoring_params.get("model_information")

        self.target_topic = blueprint.get("target_topic")
        self.expansion_config = blueprint.get("expansion")

    def _setup_traceability(
        self,
    ) -> tuple[TraceEmitter, TracedNetworkClient | None, TracedLlmHandler]:
        """TraceEmitter reads TRACE_MODE / TRACE_SAMPLE_RATE from env
        (defaults: mode="full", sample_rate=0.1). Everything downstream
        (NetworkClient, LlmHandler) gets wrapped in traced variants so
        every request/response also emits a fine-grained trace event
        (see traceability/emitter.py).
        """
        tracer = TraceEmitter.from_env(self.event_broker)
        if self.llm is not None:
            # No keys and no LLM HTTP traffic: the injected sender answers.
            return tracer, None, TracedLlmHandler(self.llm, tracer)
        if self.key_manager is None:
            self.key_manager = KeyManager(
                cooldown=self.config.llm.key_cooldown_seconds,
                keys_file=self.paths.keys_file,
            )
        fetch = self.config.fetch
        # LLM endpoints are chosen by the operator (a local server is allowed),
        # unlike page URLs, which come from crawled pages.
        traced_network = TracedNetworkClient(
            NetworkClient(
                fetch.http_total_timeout, fetch.http_connect_timeout, allow_private_addresses=True
            ),
            tracer,
        )
        traced_llm = TracedLlmHandler(
            LlmHandler(
                self.key_manager,
                client=traced_network,
                max_tokens=self.config.llm.max_tokens,
                temperature=self.config.llm.temperature,
                endpoints=self.config.providers.endpoints,
            ),
            tracer,
        )
        return tracer, traced_network, traced_llm

    async def _build_nlp_subsystem(
        self, traced_llm: TracedLlmHandler, tracer: TraceEmitter
    ) -> tuple[NLPService, SpaceUpdater, ScoringService]:
        """Builds the semantic space (NLPService/BufferManager/
        SpaceUpdater) and the LLM scoring service. `_load_blueprint_config`
        must have run first (reads self.target_topic, self.blueprint_id,
        self.expansion_config, self.scoring_*).
        """
        logger.info("Starting NLP service for crawl %s", self.crawl_id)
        buffer_manager = BufferManager(max_size=self.config.embeddings.buffer_max_size)
        nlp_service = NLPService(
            blueprint_id=self.blueprint_id,
            target_topic=self.target_topic,
            llm_handler=traced_llm,
            expansion_config=self.expansion_config,
            embedding_backend=self.config.embeddings.backend,
            model_name=self.config.embeddings.model_name,
            store_base_dir=str(self.paths.space_store_dir),
            persist_space=bool(self.expansion_config.get("persist_space", False)),
            tracer=tracer,
            buffer_manager=buffer_manager,
            composite_weights=dict(self.config.nlp.composite_weights),
            target_top_k=self.config.nlp.target_top_k,
            cluster_eps=self.config.nlp.cluster_eps,
            cluster_min_samples=self.config.nlp.cluster_min_samples,
        )
        await nlp_service.start()

        space_updater = SpaceUpdater(
            nlp_service=nlp_service,
            buffer_manager=buffer_manager,
            flush_interval=self.config.embeddings.flush_interval_seconds,
            flush_threshold=self.config.embeddings.flush_threshold,
        )

        scoring_service = ScoringService(
            traced_llm,
            self.target_topic,
            self.scoring_strategy,
            self.scoring_type,
            self.model_information,
            system_prompt=self.config.prompts.scoring_system,
            rules=self.config.prompts.scoring_rules,
            strategy_contexts=dict(self.config.prompts.strategy_contexts),
        )

        return nlp_service, space_updater, scoring_service

    def _build_pipelines(
        self,
        blueprint: dict,
        nlp_service: NLPService,
        scoring_service: ScoringService,
        fetcher: Fetcher | None = None,
    ) -> dict:
        """Build every stage from the registry in core/stages.py, keyed by
        stage, and keep them for `queue_depths` and `apply_live`. The requests
        stage fetches pages with `fetcher`, else the injected one, else its own."""
        # One budget per crawl: every scoring worker draws from the same counter.
        self.call_budget = CallBudget(self.config.llm.max_calls_per_crawl)
        self._pipelines = build_stages(
            StageInputs(
                broker=self.event_broker,
                storage=self.storage,
                config=self.config,
                paths=self.paths,
                crawl_id=self.crawl_id,
                blueprint=blueprint,
                nlp_service=nlp_service,
                scoring_service=scoring_service,
                call_budget=self.call_budget,
                fetch_concurrency=self.fetch_concurrency,
                scoring_concurrency=self.scoring_concurrency,
                seed=self.seed,
                fetcher=fetcher if fetcher is not None else self.fetcher,
            )
        )
        return self._pipelines

    def _wire_subscriptions(self, p: dict, space_updater: SpaceUpdater) -> None:
        """Subscribe every stage, then the space updater, to the events it
        names in `event_types` (pipelines.contracts.EventConsumer). This
        order is the order consumers receive an event in."""
        for consumer in (*p.values(), space_updater):
            self.event_broker.subscribe(consumer, consumer.event_types)

    def _run_manifest(self) -> dict:
        return {
            "crawl_id": self.crawl_id,
            "blueprint": self.blueprint,
            "runtime_config": self.config.model_dump(mode="json"),
            "embedding_model": self.config.embeddings.model_name,
            "llm_model": self.model_information,
            "git_sha": git_sha(),
            "seed": self.seed,
            "fetch_concurrency": self.fetch_concurrency,
            "scoring_concurrency": self.scoring_concurrency,
        }

    def _build_ui_layer(self, p: dict) -> RecordingGateway:
        """Build the UI bridge: the WebSocket gateway, the event recorder
        and the TelemetryBridge, subscribed to every event it translates."""
        obs = self.config.observability
        snapshot = CrawlStateSnapshot(
            max_candidates=obs.snapshot_max_candidates, max_errors=obs.snapshot_max_errors
        )
        ui_gateway = UIWebSocketGateway(
            snapshot,
            KeepAlive(obs.ui_ping_interval, obs.ui_ping_timeout),
            host="localhost",
            port=self.ui_port,
        )
        recorder = EventRecorder(self.paths.export_dir / self.crawl_id)
        try:
            recorder.record(snapshot.to_full_snapshot())
            recorder.write_manifest(redact_manifest(self._run_manifest()))
            recording_gateway = RecordingGateway(ui_gateway, recorder)
            telemetry = TelemetryBridge(
                snapshot,
                recording_gateway,
                priority_strategy_name=priority_strategy_name(self.blueprint, self.config),
            )
            telemetry.register_handlers()
        except BaseException:
            # Nothing owns the open event log yet, so nothing else would close it.
            recorder.close()
            raise

        self.event_broker.subscribe(telemetry, telemetry.event_types)
        # Stopping this one closes the event log as well as the server.
        return recording_gateway

    def _collect_tasks(
        self, p: dict, space_updater: SpaceUpdater, ui_gateway: RecordingGateway
    ) -> list:
        return [
            self.event_broker.start(),
            *(stage.start() for stage in p.values()),
            ui_gateway.start(),
            space_updater.start(),
        ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    crawler = Crawler("wikiMD.json")
    asyncio.run(crawler.start())
