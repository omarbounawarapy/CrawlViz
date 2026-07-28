"""Composition root for a single crawl session.

``Crawler.start()`` reads a blueprint (see ``core.boot_strapper``),
builds the ~16 pipeline objects described in the project report's
architecture chapters, wires them together through one
:class:`~core.event_broker.EventBroker`, and runs them concurrently
until a stop condition fires and every pipeline has drained (see
``pipelines.stopping_pipeline``), or until the task is cancelled from
outside (the manual STOP endpoint in ``routes.run``).
"""

import asyncio
import logging
from datetime import datetime

from config import (
    DEBUG,
    DEFAULT_PRIORITY_STRATEGY,
    EMBEDDING_BACKEND,
    EMBEDDING_MODEL,
    EXPORT_BATCH_SIZE,
    EXPORT_PATH,
    BUFFER_MAX_SIZE,
    FLUSH_INTERVAL_SECONDS,
    FLUSH_THRESHOLD,
    HIGH_SCORE_LLM_FRACTION,
    HIGH_SCORE_RANDOM_FRACTION,
    LOW_SCORE_SAMPLE_FRACTION,
    NLP_HIGH_SCORE_THRESHOLD,
    NLP_LOW_SCORE_THRESHOLD,
    SPACE_STORE_DIR,
)
from events import (
    ContentExtractedEvent,
    ContentFilteredEvent,
    EmptyScoreResultsEvent,
    ExportBatchCompletedEvent,
    ExportBatchFailedEvent,
    ExportBatchStartedEvent,
    ExportRowFailedEvent,
    ExtractionStartedEvent,
    FilteringEnqueuedEvent,
    FilteringInputSnapshotEvent,
    FilteringPipelineErrorEvent,
    FilteringWorkerCycleStartedEvent,
    HighScoreLinksEvent,
    ItemExtractionCompletedEvent,
    ItemFilteringCompletedEvent,
    LinkExtractionCompletedEvent,
    LinkFilteringCompletedEvent,
    LinksScoredEvent,
    LowScoreLinksEvent,
    NodeAddedEvent,
    NodeContentSetEvent,
    NoLinksToScoreEvent,
    PageFetchedEvent,
    PriorityCalculatedEvent,
    PriorityCalculationFailedEvent,
    PriorityCalculationStartedEvent,
    ProcessingExtractionFailedEvent,
    RequestEnqueuedEvent,
    RequestFailedEvent,
    RequestResponseReceivedEvent,
    RequestStartedEvent,
    RetryOperationFailedEvent,
    ScoreRescheduledEvent,
    ScoringCompletedEvent,
    ScoringEnqueuedEvent,
    ScoringFailedEvent,
    ScoringStartedEvent,
    StopCrawlEvent,
    StorageNodeUpdatedEvent,
    StorageOperationFailedEvent,
    TransformationCompletedEvent,
    TransformationFailedEvent,
    TransformationStartedEvent,
)
from infrastructure import KeyManager, LlmHandler, NetworkClient
from models import Storage
from nlp import BufferManager, SpaceUpdater
from pipelines import (
    CanonicalizationPipeline,
    DebuggingPipeline,
    ExportingPipeline,
    FilteringPipeline,
    LoggingPipeline,
    PriorityPipeline,
    ProcessingPipeline,
    RequestsPipeline,
    RetryProcessor,
    ScoringPipeline,
    StoppingPipeline,
    StoragePipeline,
    TransformationPipeline,
)
from services import NLPService, ScoringService
from ui_bridge import CrawlStateSnapshot, TelemetryBridge, UIWebSocketGateway

from .boot_strapper import BootStrapper
from .event_broker import EventBroker

# Traceability is a second, finer-grained event stream (see
# traceability/emitter.py) plus thin wrappers around the network/LLM
# clients that emit it -- this is what produces the granular
# "[NLP] SCORE_EMITTED" / "[LLM] DISPATCHED" trace log lines.
from traceability.emitter import TraceEmitter
from traceability.expansion_trace_events import (
    EXP_CandidatePruned,
    EXP_CandidateScored,
    EXP_PromptBuilt,
    EXP_SeedsGenerated,
    EXP_SpaceBootstrapped,
    EXP_Triggered,
)
from traceability.llm_trace_events import (
    LLM_PromptBuilt,
    LLM_RequestDispatched,
    LLM_RequestFailed,
    LLM_ResponseParsed,
    LLM_ResponseReceived,
)
from traceability.network_trace_events import (
    NET_RequestCreated,
    NET_RequestDispatched,
    NET_RequestFailed,
    NET_ResponseReceived,
    NET_RetryAttempted,
)
from traceability.nlp_trace_events import (
    NLP_FeaturesExtracted,
    NLP_InputReceived,
    NLP_ScoreEmitted,
    NLP_SimilarityScored,
    NLP_VectorComposed,
)
from traceability.traced_llm_handler import TracedLlmHandler
from traceability.traced_network_client import TracedNetworkClient

logger = logging.getLogger(__name__)


class Crawler:
    """Builds and runs one crawl session end to end.

    A Crawler is single-use: construct it with a blueprint filename,
    then ``await crawler.start()``.
    """

    def __init__(self, template_file: str):
        self.storage = Storage()
        self.template_file = template_file
        self.event_broker = EventBroker()
        self.key_manager = KeyManager()
        self.crawl_id = (
            template_file[: template_file.find(".")]
            + "-"
            + datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
        )

    async def start(self) -> None:
        blueprint = await BootStrapper(
            self.event_broker,
            self.storage,
            self.template_file,
        ).bootstrap()

        self._load_blueprint_config(blueprint)

        tracer, traced_network, traced_llm = self._setup_traceability()

        nlp_service, space_updater, scoring_service = await self._build_nlp_subsystem(
            traced_llm, tracer
        )

        pipelines = self._build_pipelines(blueprint, nlp_service, scoring_service)
        self._wire_subscriptions(pipelines, space_updater)
        ui_gateway = self._build_ui_layer(pipelines)

        tasks = self._collect_tasks(pipelines, space_updater, ui_gateway)
        try:
            await asyncio.gather(*tasks)
        finally:
            # Two separate aiohttp.ClientSessions get opened for this
            # crawl -- requests_pipeline.network_client (page fetches)
            # and traced_network (LLM calls) -- and neither was ever
            # explicitly closed, which leaks connectors and logs
            # "Unclosed client session" warnings on any server that runs
            # more than one crawl per process lifetime. `finally` so this
            # still runs if a pipeline task raises.
            await pipelines["requests"].network_client.close()
            await traced_network.close()

    # =========================================================
    # COMPOSITION STEPS
    # =========================================================
    # Split out of what used to be one ~250-line start() method so each
    # piece of the wiring can be read (and, eventually, tested) on its
    # own. Behavior is unchanged -- this is a pure decomposition.

    def _load_blueprint_config(self, blueprint: dict) -> None:
        """Unpack the blueprint into the attributes the rest of this
        class (and StoppingPipeline, which reads several of these
        directly off `self`) expects.
        """
        self.blueprint = blueprint
        self.blueprint_id = blueprint.get("blueprint_id")
        self.extraction_blueprint = blueprint.get("extraction")

        self.stop_conditions = blueprint.get("stop_conditions")
        self.max_nodes = self.stop_conditions["max_nodes"]
        self.max_depth = self.stop_conditions["max_depth"]
        self.max_duration = self.stop_conditions["max_duration"]
        self.no_progress_timeout = self.stop_conditions["no_progress_timeout"]
        self.target_url = self.stop_conditions["stop_url"]

        self.scoring_config = blueprint.get("scoring")
        self.scoring_strategy = self.scoring_config.get("strategy")
        self.scoring_params = self.scoring_config.get("params")
        self.scoring_type = self.scoring_params.get("scoring_type")
        self.model_information = self.scoring_params.get("model_information")

        self.target_topic = blueprint.get("target_topic")
        self.expansion_config = blueprint.get("expansion")

    def _setup_traceability(self) -> tuple[TraceEmitter, TracedNetworkClient, TracedLlmHandler]:
        """TraceEmitter reads TRACE_MODE / TRACE_SAMPLE_RATE from env
        (defaults: mode="full", sample_rate=0.1). Everything downstream
        (NetworkClient, LlmHandler) gets wrapped in traced variants so
        every request/response also emits a fine-grained trace event
        (see traceability/emitter.py).
        """
        tracer = TraceEmitter.from_env(self.event_broker)
        traced_network = TracedNetworkClient(NetworkClient(), tracer)
        traced_llm = TracedLlmHandler(
            LlmHandler(self.key_manager, client=traced_network), tracer
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
        buffer_manager = BufferManager(max_size=BUFFER_MAX_SIZE)
        nlp_service = NLPService(
            blueprint_id=self.blueprint_id,
            target_topic=self.target_topic,
            llm_handler=traced_llm,
            expansion_config=self.expansion_config,
            embedding_backend=EMBEDDING_BACKEND,
            model_name=EMBEDDING_MODEL,
            store_base_dir=SPACE_STORE_DIR,
            tracer=tracer,
            buffer_manager=buffer_manager,
        )
        await nlp_service.start()

        space_updater = SpaceUpdater(
            nlp_service=nlp_service,
            buffer_manager=buffer_manager,
            flush_interval=FLUSH_INTERVAL_SECONDS,
            flush_threshold=FLUSH_THRESHOLD,
        )

        scoring_service = ScoringService(
            traced_llm,
            self.target_topic,
            self.scoring_strategy,
            self.scoring_type,
            self.model_information,
        )

        return nlp_service, space_updater, scoring_service

    def _build_pipelines(
        self, blueprint: dict, nlp_service: NLPService, scoring_service: ScoringService
    ) -> dict:
        """Construct every pipeline.

        Returns a name -> instance dict rather than ~14 separate local
        variables, since both `_wire_subscriptions` and `_collect_tasks`
        need to look most of them up individually, and a dict makes that
        an explicit, greppable key rather than relying on closure scope.
        """
        p: dict = {}

        p["processing"] = ProcessingPipeline(self.event_broker, self.extraction_blueprint)
        p["requests"] = RequestsPipeline(self.event_broker)
        p["scoring"] = ScoringPipeline(
            scoring_service,
            nlp_service,
            self.event_broker,
            low_threshold=NLP_LOW_SCORE_THRESHOLD,
            high_threshold=NLP_HIGH_SCORE_THRESHOLD,
            high_score_llm_fraction=HIGH_SCORE_LLM_FRACTION,
            low_score_sample_fraction=LOW_SCORE_SAMPLE_FRACTION,
            high_score_random_fraction=HIGH_SCORE_RANDOM_FRACTION,
        )
        p["storage"] = StoragePipeline(self.storage, self.event_broker)
        p["filtering"] = FilteringPipeline(self.event_broker, self.storage)
        p["priority"] = PriorityPipeline(
            self.storage,
            self.event_broker,
            strategy_name=self.stop_conditions.get(
                "priority_strategy", DEFAULT_PRIORITY_STRATEGY
            ),
        )
        p["logging"] = LoggingPipeline(self.event_broker, self.crawl_id)
        p["stopping"] = StoppingPipeline(self)
        p["debug"] = DebuggingPipeline(self.event_broker, self.crawl_id, enabled=DEBUG)
        p["transformation"] = TransformationPipeline(self.event_broker, self.extraction_blueprint)
        p["exporting"] = ExportingPipeline(
            self.crawl_id,
            self.blueprint_id,
            blueprint,
            self.event_broker,
            batch_size=EXPORT_BATCH_SIZE,
        )
        p["canon"] = CanonicalizationPipeline(
            self.crawl_id, self.event_broker, export_path=EXPORT_PATH
        )
        p["retry"] = RetryProcessor(
            self.storage, self.event_broker, requests_pipeline=p["requests"]
        )

        return p

    def _wire_subscriptions(self, p: dict, space_updater: SpaceUpdater) -> None:
        """All EventBroker.subscribe() calls in one place -- this is the
        "who reacts to what" map for the whole crawl. Adding a new
        pipeline means adding both a `_build_pipelines` entry and a
        subscription here; nothing currently enforces both halves get
        done (see the engineering audit's note on this being the root
        cause of two bugs already found and fixed this session).
        """
        b = self.event_broker

        b.subscribe(p["retry"], [EmptyScoreResultsEvent, RequestFailedEvent])

        # SpaceUpdater's flush loop otherwise runs forever -- this is
        # what lets it notice the crawl ended and actually stop (see
        # nlp/space_updater.py's docstring).
        b.subscribe(space_updater, [StopCrawlEvent])

        b.subscribe(
            p["logging"],
            [
                NodeAddedEvent,
                PageFetchedEvent,
                ContentFilteredEvent,
                LinksScoredEvent,
                PriorityCalculatedEvent,
                TransformationCompletedEvent,
                ExportBatchCompletedEvent,
                ScoreRescheduledEvent,
                StopCrawlEvent,
            ],
        )

        b.subscribe(p["canon"], [PageFetchedEvent])

        b.subscribe(
            p["debug"],
            [
                RequestStartedEvent,
                RequestResponseReceivedEvent,
                RequestFailedEvent,
                ExtractionStartedEvent,
                LinkExtractionCompletedEvent,
                ItemExtractionCompletedEvent,
                # ProcessingExtractionFailedEvent / FilteringPipelineErrorEvent:
                # DebuggingPipeline.handlers already had _extraction_failed /
                # _filter_failed implemented for these -- they just weren't
                # subscribed, so extraction/filtering exceptions produced no
                # log line and no UI signal at all (V2 audit §A.1.2).
                ProcessingExtractionFailedEvent,
                FilteringPipelineErrorEvent,
                FilteringInputSnapshotEvent,
                LinkFilteringCompletedEvent,
                ItemFilteringCompletedEvent,
                ScoringStartedEvent,
                ScoringCompletedEvent,
                ScoringFailedEvent,
                PriorityCalculationStartedEvent,
                PriorityCalculatedEvent,
                PriorityCalculationFailedEvent,
                TransformationStartedEvent,
                TransformationCompletedEvent,
                TransformationFailedEvent,
                ExportBatchFailedEvent,
                ExportBatchStartedEvent,
                ExportRowFailedEvent,
                RetryOperationFailedEvent,
                EmptyScoreResultsEvent,
                NoLinksToScoreEvent,
                NodeContentSetEvent,
                # trace events routed into the same debug pipeline
                NLP_InputReceived,
                NLP_FeaturesExtracted,
                NLP_SimilarityScored,
                NLP_VectorComposed,
                NLP_ScoreEmitted,
                LLM_PromptBuilt,
                LLM_RequestDispatched,
                LLM_ResponseReceived,
                LLM_ResponseParsed,
                LLM_RequestFailed,
                NET_RequestCreated,
                NET_RequestDispatched,
                NET_ResponseReceived,
                NET_RequestFailed,
                NET_RetryAttempted,
                EXP_Triggered,
                EXP_PromptBuilt,
                EXP_SeedsGenerated,
                EXP_CandidateScored,
                EXP_CandidatePruned,
                EXP_SpaceBootstrapped,
            ],
        )

        b.subscribe(p["processing"], [PageFetchedEvent])
        b.subscribe(p["requests"], [NodeAddedEvent])
        b.subscribe(p["scoring"], [NodeAddedEvent, ScoreRescheduledEvent])
        b.subscribe(p["filtering"], [ContentExtractedEvent])
        # NOTE (V2 audit finding, see docs/V2_ARCHITECTURE.md §A.1.1): PriorityPipeline's
        # own handler table has always mapped HighScoreLinksEvent -> _on_links_scored,
        # but it was never actually subscribed to receive that event type. That bucket
        # is exactly the links the cascade is confident about and deliberately skips an
        # LLM call for -- the entire cost-saving half of the cascade -- and without this
        # subscription they were scored, correctly bucketed, and then silently dropped:
        # never prioritized, never stored, never expanded into the frontier. Restoring
        # this line is a correctness fix, not a feature addition.
        b.subscribe(p["priority"], [LinksScoredEvent, HighScoreLinksEvent])
        b.subscribe(p["transformation"], [ContentFilteredEvent])
        b.subscribe(
            p["storage"],
            [PriorityCalculatedEvent, TransformationCompletedEvent, PageFetchedEvent],
        )
        b.subscribe(p["exporting"], [TransformationCompletedEvent, StopCrawlEvent])
        b.subscribe(
            p["stopping"],
            [NodeAddedEvent, StorageNodeUpdatedEvent, StopCrawlEvent],
        )

    def _build_ui_layer(self, p: dict) -> UIWebSocketGateway:
        """Wire TelemetryBridge -- see docs/V2_ARCHITECTURE.md §B.2.1.

        V1's UIEventTranslator subscribed to 7 event types. This subscribes
        to everything TelemetryBridge knows how to translate: the original
        7 (unchanged behavior) plus every pipeline stage's start/complete/
        fail events, the scoring cascade's two candidate-decision events,
        and every previously-orphaned failure event. This is the single
        change that unlocks Pipeline Monitor, candidate/frontier visibility,
        the Node Inspector's scoring breakdown, and crawl-wide error
        visibility -- none of it required new backend instrumentation, only
        a wider subscription list and a bigger translator.
        """
        snapshot = CrawlStateSnapshot()
        ui_gateway = UIWebSocketGateway(snapshot, host="localhost", port=8765)
        telemetry = TelemetryBridge(
            snapshot,
            ui_gateway,
            priority_strategy_name=self.stop_conditions.get(
                "priority_strategy", DEFAULT_PRIORITY_STRATEGY
            ),
        )
        telemetry.register_handlers()

        self.event_broker.subscribe(
            telemetry,
            [
                # V1 node lifecycle (unchanged)
                NodeAddedEvent,
                PageFetchedEvent,
                ContentFilteredEvent,
                LinksScoredEvent,
                PriorityCalculatedEvent,
                StorageNodeUpdatedEvent,
                StopCrawlEvent,
                # V2: request stage
                RequestEnqueuedEvent,
                RequestStartedEvent,
                RequestResponseReceivedEvent,
                RequestFailedEvent,
                # V2: extraction stage
                ExtractionStartedEvent,
                LinkExtractionCompletedEvent,
                ProcessingExtractionFailedEvent,
                # V2: filtering stage
                FilteringEnqueuedEvent,
                FilteringWorkerCycleStartedEvent,
                FilteringPipelineErrorEvent,
                # V2: scoring stage + cascade candidate visibility
                ScoringEnqueuedEvent,
                ScoringStartedEvent,
                ScoringCompletedEvent,
                ScoringFailedEvent,
                HighScoreLinksEvent,
                LowScoreLinksEvent,
                # V2: priority stage
                PriorityCalculationStartedEvent,
                PriorityCalculationFailedEvent,
                # V2: transformation stage
                TransformationStartedEvent,
                TransformationCompletedEvent,
                TransformationFailedEvent,
                # V2: export stage
                ExportBatchStartedEvent,
                ExportBatchCompletedEvent,
                ExportBatchFailedEvent,
                ExportRowFailedEvent,
                # V2: crawl-wide errors
                StorageOperationFailedEvent,
                RetryOperationFailedEvent,
            ],
        )
        return ui_gateway

    def _collect_tasks(
        self, p: dict, space_updater: SpaceUpdater, ui_gateway: UIWebSocketGateway
    ) -> list:
        return [
            self.event_broker.start(),
            p["logging"].start(),
            p["requests"].start(),
            p["processing"].start(),
            p["filtering"].start(),
            p["scoring"].start(),
            p["priority"].start(),
            p["storage"].start(),
            p["debug"].start(),
            p["stopping"].start(),
            p["transformation"].start(),
            p["exporting"].start(),
            p["canon"].start(),
            p["retry"].start(),
            ui_gateway.start(),
            space_updater.start(),
        ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    crawler = Crawler("wikiMD.json")
    asyncio.run(crawler.start())
