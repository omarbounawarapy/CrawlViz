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
    EmptyScoreResults,
    ExportBatchCompletedEvent,
    ExportBatchFailedEvent,
    ExportBatchStartedEvent,
    ExportRowFailedEvent,
    ExtractionStartedEvent,
    FilteringInputSnapshotEvent,
    ItemExtractionCompletedEvent,
    ItemFilteringCompletedEvent,
    LinkExtractionCompletedEvent,
    LinkFilteringCompletedEvent,
    LinksScoredEvent,
    NodeAddedEvent,
    NodeContentSetEvent,
    NoLinksToScoreEvent,
    PageFetchedEvent,
    PriorityCalculatedEvent,
    PriorityCalculationFailedEvent,
    PriorityCalculationStartedEvent,
    RequestFailedEvent,
    RequestResponseReceivedEvent,
    RequestStartedEvent,
    RetryOperationFailedEvent,
    ScoreRescheduledEvent,
    ScoringCompletedEvent,
    ScoringFailedEvent,
    ScoringStartedEvent,
    StopCrawlEvent,
    StorageNodeUpdatedEvent,
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
from ui_bridge import CrawlStateSnapshot, UIEventTranslator, UIWebSocketGateway

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

        self.blueprint = blueprint
        self.blueprint_id = blueprint.get("blueprint_id")
        self.extraction_blueprint = blueprint.get("extraction")

        stop_conditions = blueprint.get("stop_conditions")
        self.max_nodes = stop_conditions["max_nodes"]
        self.max_depth = stop_conditions["max_depth"]
        self.max_duration = stop_conditions["max_duration"]
        self.no_progress_timeout = stop_conditions["no_progress_timeout"]
        self.target_url = stop_conditions["stop_url"]

        self.scoring_config = blueprint.get("scoring")
        self.scoring_strategy = self.scoring_config.get("strategy")
        self.scoring_params = self.scoring_config.get("params")
        self.scoring_type = self.scoring_params.get("scoring_type")
        self.model_information = self.scoring_params.get("model_information")

        # ── Traceability ─────────────────────────────────────────────
        # TraceEmitter reads TRACE_MODE / TRACE_SAMPLE_RATE from env
        # (defaults: mode="full", sample_rate=0.1).
        tracer = TraceEmitter.from_env(self.event_broker)
        traced_network = TracedNetworkClient(NetworkClient(), tracer)
        traced_llm = TracedLlmHandler(
            LlmHandler(self.key_manager, client=traced_network), tracer
        )

        # ── NLP subsystem ────────────────────────────────────────────
        self.target_topic = blueprint.get("target_topic")
        expansion_config = blueprint.get("expansion")

        logger.info("Starting NLP service for crawl %s", self.crawl_id)
        nlp_service = NLPService(
            blueprint_id=self.blueprint_id,
            target_topic=self.target_topic,
            llm_handler=traced_llm,
            expansion_config=expansion_config,
            embedding_backend=EMBEDDING_BACKEND,
            model_name=EMBEDDING_MODEL,
            store_base_dir=SPACE_STORE_DIR,
            tracer=tracer,
        )
        await nlp_service.start()

        buffer_manager = BufferManager(max_size=BUFFER_MAX_SIZE)
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

        # ── Pipelines ────────────────────────────────────────────────
        processing_pipeline = ProcessingPipeline(self.event_broker, self.extraction_blueprint)
        requests_pipeline = RequestsPipeline(self.event_broker)
        scoring_pipeline = ScoringPipeline(
            scoring_service,
            nlp_service,
            self.event_broker,
            low_threshold=NLP_LOW_SCORE_THRESHOLD,
            high_threshold=NLP_HIGH_SCORE_THRESHOLD,
            high_score_llm_fraction=HIGH_SCORE_LLM_FRACTION,
            low_score_sample_fraction=LOW_SCORE_SAMPLE_FRACTION,
            high_score_random_fraction=HIGH_SCORE_RANDOM_FRACTION,
        )
        storage_pipeline = StoragePipeline(self.storage, self.event_broker)
        filtering_pipeline = FilteringPipeline(self.event_broker, self.storage)
        priority_pipeline = PriorityPipeline(
            self.storage,
            self.event_broker,
            strategy_name=stop_conditions.get("priority_strategy", DEFAULT_PRIORITY_STRATEGY),
        )
        logging_pipeline = LoggingPipeline(self.event_broker, self.crawl_id)
        stopping_pipeline = StoppingPipeline(self)
        debug_pipeline = DebuggingPipeline(self.event_broker, self.crawl_id, enabled=DEBUG)
        transformation_pipeline = TransformationPipeline(self.event_broker, self.extraction_blueprint)
        exporting_pipeline = ExportingPipeline(
            self.crawl_id,
            self.blueprint_id,
            blueprint,
            self.event_broker,
            batch_size=EXPORT_BATCH_SIZE,
        )
        canon_pipeline = CanonicalizationPipeline(
            self.crawl_id, self.event_broker, export_path=EXPORT_PATH
        )
        retry_processor = RetryProcessor(self.storage, self.event_broker)

        # ── Subscriptions ────────────────────────────────────────────
        self.event_broker.subscribe(retry_processor, [EmptyScoreResults])

        self.event_broker.subscribe(
            logging_pipeline,
            [
                NodeAddedEvent,
                PageFetchedEvent,
                ContentFilteredEvent,
                LinksScoredEvent,
                PriorityCalculatedEvent,
                TransformationCompletedEvent,
                ExportBatchCompletedEvent,
                ScoreRescheduledEvent,
            ],
        )

        self.event_broker.subscribe(canon_pipeline, [PageFetchedEvent, StopCrawlEvent])

        self.event_broker.subscribe(
            debug_pipeline,
            [
                RequestStartedEvent,
                RequestResponseReceivedEvent,
                RequestFailedEvent,
                ExtractionStartedEvent,
                LinkExtractionCompletedEvent,
                ItemExtractionCompletedEvent,
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
                EmptyScoreResults,
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

        self.event_broker.subscribe(processing_pipeline, [PageFetchedEvent])
        self.event_broker.subscribe(requests_pipeline, [NodeAddedEvent])
        self.event_broker.subscribe(
            scoring_pipeline, [NodeAddedEvent, ScoreRescheduledEvent]
        )
        self.event_broker.subscribe(filtering_pipeline, [ContentExtractedEvent])
        self.event_broker.subscribe(priority_pipeline, [LinksScoredEvent])
        self.event_broker.subscribe(transformation_pipeline, [ContentFilteredEvent])
        self.event_broker.subscribe(
            storage_pipeline,
            [PriorityCalculatedEvent, TransformationCompletedEvent, PageFetchedEvent],
        )
        self.event_broker.subscribe(
            exporting_pipeline, [TransformationCompletedEvent, StopCrawlEvent]
        )
        self.event_broker.subscribe(
            stopping_pipeline,
            [NodeAddedEvent, StorageNodeUpdatedEvent, StopCrawlEvent],
        )

        # ── UI layer ─────────────────────────────────────────────────
        snapshot = CrawlStateSnapshot()
        ui_gateway = UIWebSocketGateway(snapshot, host="localhost", port=8765)
        ui_translator = UIEventTranslator(snapshot, ui_gateway)
        ui_translator.register_handlers()

        self.event_broker.subscribe(
            ui_translator,
            [
                NodeAddedEvent,
                PageFetchedEvent,
                ContentFilteredEvent,
                LinksScoredEvent,
                PriorityCalculatedEvent,
                StorageNodeUpdatedEvent,
                StopCrawlEvent,
            ],
        )

        tasks = [
            self.event_broker.start(),
            logging_pipeline.start(),
            requests_pipeline.start(),
            processing_pipeline.start(),
            filtering_pipeline.start(),
            scoring_pipeline.start(),
            priority_pipeline.start(),
            storage_pipeline.start(),
            debug_pipeline.start(),
            stopping_pipeline.start(),
            transformation_pipeline.start(),
            exporting_pipeline.start(),
            canon_pipeline.start(),
            retry_processor.start(),
            ui_gateway.start(),
            space_updater.start(),
        ]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    crawler = Crawler("wikiMD.json")
    asyncio.run(crawler.start())
