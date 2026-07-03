import asyncio
from datetime import datetime
from urllib.parse import unquote
import os

from infrastructure import LogWriter

from events import (
    # REQUESTS
    RequestStartedEvent,
    RequestResponseReceivedEvent,
    RequestFailedEvent,

    # PROCESSING / EXTRACTION
    ExtractionStartedEvent,
    LinkExtractionCompletedEvent,
    ItemExtractionCompletedEvent,
    ProcessingExtractionFailedEvent,

    # FILTERING
    FilteringInputSnapshotEvent,
    LinkFilteringCompletedEvent,
    ItemFilteringCompletedEvent,
    FilteringPipelineErrorEvent,

    # SCORING
    ScoringStartedEvent,
    ScoringCompletedEvent,
    ScoringFailedEvent,
    EmptyScoreResults,
    NoLinksToScoreEvent,

    # PRIORITY
    PriorityCalculationStartedEvent,
    PriorityCalculatedEvent,
    PriorityCalculationFailedEvent,

    # TRANSFORMATION
    TransformationStartedEvent,
    TransformationCompletedEvent,
    TransformationFailedEvent,

    # STORAGE
    NodeContentSetEvent,

    # EXPORT
    ExportBatchFailedEvent,
    ExportBatchStartedEvent,
    ExportRowFailedEvent,

    # RETRY
    RetryOperationFailedEvent,
)

# ── TRACE EVENTS ──────────────────────────────────────────────────────────────
from traceability.nlp_trace_events import (
    NLP_InputReceived,
    NLP_FeaturesExtracted,
    NLP_SimilarityScored,
    NLP_VectorComposed,
    NLP_ScoreEmitted,
)
from traceability.llm_trace_events import (
    LLM_PromptBuilt,
    LLM_RequestDispatched,
    LLM_ResponseReceived,
    LLM_ResponseParsed,
    LLM_RequestFailed,
)
from traceability.network_trace_events import (
    NET_RequestCreated,
    NET_RequestDispatched,
    NET_ResponseReceived,
    NET_RequestFailed,
    NET_RetryAttempted,
)
from traceability.expansion_trace_events import (
    EXP_Triggered,
    EXP_PromptBuilt,
    EXP_SeedsGenerated,
    EXP_CandidateScored,
    EXP_CandidatePruned,
    EXP_SpaceBootstrapped,
)


class DebuggingPipeline:
    def __init__(self, event_broker, crawl_id, enabled=True, max_queue_size=0, max_concurrency=2):
        self.event_broker = event_broker
        self.enabled = enabled

        debug_dir = os.path.join("debug", crawl_id[:crawl_id.find("-")])
        os.makedirs(debug_dir, exist_ok=True)

        path = os.path.join(debug_dir, crawl_id)
        self.log_writer = LogWriter(path)

        self.queue = asyncio.Queue(maxsize=max_queue_size)
        self.max_concurrency = max_concurrency
        self.workers = []

        self.handlers = {
            # REQUESTS
            RequestStartedEvent: self._request_started,
            RequestResponseReceivedEvent: self._response_received,
            RequestFailedEvent: self._request_failed,

            # EXTRACTION
            ExtractionStartedEvent: self._extraction_started,
            LinkExtractionCompletedEvent: self._links_extracted,
            ItemExtractionCompletedEvent: self._items_extracted,
            ProcessingExtractionFailedEvent: self._extraction_failed,

            # FILTERING
            FilteringInputSnapshotEvent: self._filter_input,
            LinkFilteringCompletedEvent: self._link_filter,
            ItemFilteringCompletedEvent: self._item_filter,
            FilteringPipelineErrorEvent: self._filter_failed,

            # TRANSFORMATION
            TransformationStartedEvent: self._transformation_started,
            TransformationCompletedEvent: self._transformation_done,
            TransformationFailedEvent: self._transformation_failed,

            # SCORING
            ScoringStartedEvent: self._scoring_started,
            ScoringCompletedEvent: self._scoring_done,
            ScoringFailedEvent: self._scoring_failed,
            EmptyScoreResults: self._empty_score,
            NoLinksToScoreEvent: self._no_links_to_score,

            # STORAGE
            NodeContentSetEvent: self._content_set,

            # PRIORITY
            PriorityCalculationStartedEvent: self._priority_started,
            PriorityCalculatedEvent: self._priority_done,
            PriorityCalculationFailedEvent: self._priority_failed,

            # EXPORT
            ExportRowFailedEvent: self._export_row_failed,
            ExportBatchFailedEvent: self._export_failed_event,
            ExportBatchStartedEvent: self._export_batch_started,

            # RETRY
            RetryOperationFailedEvent: self._retry_failed,

            # ── NLP TRACE ─────────────────────────────────────────────────────
            NLP_InputReceived: self._nlp_input_received,
            NLP_FeaturesExtracted: self._nlp_features_extracted,
            NLP_SimilarityScored: self._nlp_similarity_scored,
            NLP_VectorComposed: self._nlp_vector_composed,
            NLP_ScoreEmitted: self._nlp_score_emitted,

            # ── LLM TRACE ─────────────────────────────────────────────────────
            LLM_PromptBuilt: self._llm_prompt_built,
            LLM_RequestDispatched: self._llm_request_dispatched,
            LLM_ResponseReceived: self._llm_response_received,
            LLM_ResponseParsed: self._llm_response_parsed,
            LLM_RequestFailed: self._llm_request_failed,

            # ── NETWORK TRACE ─────────────────────────────────────────────────
            NET_RequestCreated: self._net_request_created,
            NET_RequestDispatched: self._net_request_dispatched,
            NET_ResponseReceived: self._net_response_received,
            NET_RequestFailed: self._net_request_failed,
            NET_RetryAttempted: self._net_retry_attempted,

            # ── EXPANSION TRACE ───────────────────────────────────────────────
            EXP_Triggered: self._exp_triggered,
            EXP_PromptBuilt: self._exp_prompt_built,
            EXP_SeedsGenerated: self._exp_seeds_generated,
            EXP_CandidateScored: self._exp_candidate_scored,
            EXP_CandidatePruned: self._exp_candidate_pruned,
            EXP_SpaceBootstrapped: self._exp_space_bootstrapped,
        }

    # =====================================================
    # ENTRY
    # =====================================================
    async def put(self, event):
        if self.enabled:
            await self.queue.put(event)

    # =====================================================
    # START
    # =====================================================
    async def start(self):
        if not self.enabled:
            return

        await self.log_writer.create_log_file()

        self.workers = [
            asyncio.create_task(self.worker(i))
            for i in range(self.max_concurrency)
        ]

        await asyncio.gather(*self.workers)

    # =====================================================
    # WORKER
    # =====================================================
    async def worker(self, worker_id):
        while self.queue and self.event_broker.running:
            event = await self.queue.get()

            try:
                handler = self.handlers.get(type(event))
                if handler:
                    log = handler(event, worker_id)
                    await self.log_writer.write_log(log)

            except Exception as e:
                await self.log_writer.write_log(
                    f"[DEBUG_ERROR] event={type(event).__name__} error={str(e)}"
                )

            finally:
                self.queue.task_done()

    # =====================================================
    # HELPERS
    # =====================================================
    def _prefix(self, w):
        now = datetime.now()
        t = now.strftime("%H:%M:%S") + f".{int(now.microsecond/1000):03d}"
        return f"[{t}][DW{w}]"

    def _clean(self, url):
        return unquote(url)

    def _truncate(self, s, n=120):
        return s[:n] + "…" if len(s) > n else s

    def _tid(self, e):
        return getattr(e, "trace_id", "")[:8]

    # =====================================================
    # EXISTING HANDLERS (unchanged)
    # =====================================================
    def _request_started(self, e, w):
        return f"{self._prefix(w)} [REQ] START {self._clean(e.url)}"

    def _response_received(self, e, w):
        return f"{self._prefix(w)} [REQ] RESPONSE size={e.response_size}"

    def _request_failed(self, e, w):
        return f"{self._prefix(w)} [REQ] FAILED error={e.error_message}"

    def _extraction_started(self, e, w):
        return f"{self._prefix(w)} [EXTRACT] START node={e.node_id}"

    def _links_extracted(self, e, w):
        return f"{self._prefix(w)} [EXTRACT] LINKS count={e.extracted_links_count}"

    def _items_extracted(self, e, w):
        return f"{self._prefix(w)} [EXTRACT] ITEMS count={e.extracted_items_count}"

    def _extraction_failed(self, e, w):
        return f"{self._prefix(w)} [EXTRACT] FAILED {e.error_message}"

    def _filter_input(self, e, w):
        return f"{self._prefix(w)} [FILTER] INPUT links={e.raw_links_count} items={e.raw_items_count}"

    def _link_filter(self, e, w):
        return f"{self._prefix(w)} [FILTER] LINKS kept={len(e.accepted)} rejected={e.rejected_count}"

    def _item_filter(self, e, w):
        return f"{self._prefix(w)} [FILTER] ITEMS kept={len(e.accepted)} rejected={e.rejected_count}"

    def _filter_failed(self, e, w):
        return f"{self._prefix(w)} [FILTER] FAILED stage={e.stage} error={e.error_message}"

    def _transformation_started(self, e, w):
        return f"{self._prefix(w)} [TRANSFORM] START node={e.node_id} items={e.items_count}"

    def _transformation_done(self, e, w):
        return f"{self._prefix(w)} [TRANSFORM] DONE items={len(e.transformed_items)}"

    def _transformation_failed(self, e, w):
        return f"{self._prefix(w)} [TRANSFORM] FAILED error={e.error_message}"

    def _scoring_started(self, e, w):
        return f"{self._prefix(w)} [SCORING] START node={e.node_id}"

    def _scoring_done(self, e, w):
        return f"{self._prefix(w)} [SCORING] DONE count={e.output_count}"

    def _scoring_failed(self, e, w):
        return f"{self._prefix(w)} [SCORING] FAILED {e.error_message}"

    def _content_set(self, e, w):
        return f"{self._prefix(w)} [STORAGE] CONTENT SET node={e.correlation_id}"

    def _priority_started(self, e, w):
        return f"{self._prefix(w)} [PRIORITY] START node={e.node_id}"

    def _priority_done(self, e, w):
        return f"{self._prefix(w)} [PRIORITY] DONE output={e.output_count}"

    def _priority_failed(self, e, w):
        return f"{self._prefix(w)} [PRIORITY] FAILED {e.error_message}"

    def _export_batch_started(self, e, w):
        return (
            f"{self._prefix(w)} [EXPORT] BATCH_START "
            f"table={self._clean(e.table)} size={e.batch_size}"
        )

    def _export_failed_event(self, e, w):
        return (
            f"{self._prefix(w)} [EXPORT] BATCH_FAIL "
            f"table={self._clean(e.table)} "
            f"error={e.error_type}: {self._clean(e.error_message)}"
        )

    def _export_row_failed(self, e, w):
        return (
            f"{self._prefix(w)} [EXPORT] ROW_FAIL "
            f"table={self._clean(e.table)} "
            f"field={e.field} "
            f"value={self._truncate(str(e.value))} "
            f"error={e.error_type}"
        )

    def _empty_score(self, e, w):
        return f"{self._prefix(w)} [SCORING] EMPTY_RESULT node={e.node.get_id()}"

    def _retry_failed(self, e, w):
        return (
            f"{self._prefix(w)} [RETRY] FAILED "
            f"stage={self._clean(e.stage)} "
            f"error_type={e.error_type} "
            f"error_message={self._truncate(e.error_message)}"
        )

    def _no_links_to_score(self, e, w):
        return f"{self._prefix(w)} [SCORING] NO_LINKS node={e.node.get_id()}"

    # =====================================================
    # NLP TRACE HANDLERS
    # =====================================================

    def _nlp_input_received(self, e, w):
        return (
            f"{self._prefix(w)} [NLP] INPUT "
            f"tid={self._tid(e)} node={e.node_id} "
            f"url={self._truncate(e.link_url, 60)} "
            f"space_size={e.space_size}"
        )

    def _nlp_features_extracted(self, e, w):
        top = {k: round(v, 4) for k, v in e.features.items()}
        return (
            f"{self._prefix(w)} [NLP] FEATURES "
            f"tid={self._tid(e)} node={e.node_id} "
            f"url={self._truncate(e.link_url, 60)} "
            f"features={top}"
        )

    def _nlp_similarity_scored(self, e, w):
        return (
            f"{self._prefix(w)} [NLP] SIMILARITY "
            f"tid={self._tid(e)} node={e.node_id} "
            f"url={self._truncate(e.link_url, 60)} "
            f"target_sim={round(e.target_similarity, 4)} "
            f"novelty={round(e.novelty_injection, 4)} "
            f"density={round(e.region_density, 4)} "
            f"gap={round(e.coverage_gap, 4)}"
        )

    def _nlp_vector_composed(self, e, w):
        return (
            f"{self._prefix(w)} [NLP] COMPOSED "
            f"tid={self._tid(e)} node={e.node_id} "
            f"url={self._truncate(e.link_url, 60)} "
            f"raw_sum={round(e.raw_sum, 4)} "
            f"final_score={round(e.final_score, 4)}"
        )

    def _nlp_score_emitted(self, e, w):
        return (
            f"{self._prefix(w)} [NLP] SCORE_EMITTED "
            f"tid={self._tid(e)} node={e.node_id} "
            f"url={self._truncate(e.link_url, 60)} "
            f"nlp_score={round(e.nlp_score, 4)} "
            f"space_v={e.space_version}"
        )

    # =====================================================
    # LLM TRACE HANDLERS
    # =====================================================

    def _llm_prompt_built(self, e, w):
        return (
            f"{self._prefix(w)} [LLM] PROMPT_BUILT "
            f"tid={self._tid(e)} node={e.node_id} "
            f"req={e.request_id} "
            f"type={e.llm_type} model={e.model} "
            f"len={e.prompt_len} strategy={e.strategy}"
        )

    def _llm_request_dispatched(self, e, w):
        return (
            f"{self._prefix(w)} [LLM] DISPATCHED "
            f"tid={self._tid(e)} node={e.node_id} "
            f"req={e.request_id} type={e.llm_type} model={e.model}"
        )

    def _llm_response_received(self, e, w):
        return (
            f"{self._prefix(w)} [LLM] RESPONSE "
            f"tid={self._tid(e)} node={e.node_id} "
            f"req={e.request_id} "
            f"ok={e.status_ok} latency_ms={round(e.latency_ms, 1)}"
        )

    def _llm_response_parsed(self, e, w):
        usage = e.token_usage or {}
        return (
            f"{self._prefix(w)} [LLM] PARSED "
            f"tid={self._tid(e)} node={e.node_id} "
            f"req={e.request_id} "
            f"keys={e.output_keys} "
            f"tokens={usage}"
        )

    def _llm_request_failed(self, e, w):
        return (
            f"{self._prefix(w)} [LLM] FAILED "
            f"tid={self._tid(e)} node={e.node_id} "
            f"req={e.request_id} stage={e.stage} "
            f"error={e.error_type}: {self._truncate(e.error_message)}"
        )

    # =====================================================
    # NETWORK TRACE HANDLERS
    # =====================================================

    def _net_request_created(self, e, w):
        return (
            f"{self._prefix(w)} [NET] CREATED "
            f"tid={self._tid(e)} node={e.node_id} "
            f"req={e.request_id} "
            f"method={e.method} url={self._truncate(e.url, 80)} "
            f"auth={e.has_auth_header}"
        )

    def _net_request_dispatched(self, e, w):
        return (
            f"{self._prefix(w)} [NET] DISPATCHED "
            f"tid={self._tid(e)} node={e.node_id} "
            f"req={e.request_id} strategy={e.strategy_class}"
        )

    def _net_response_received(self, e, w):
        return (
            f"{self._prefix(w)} [NET] RESPONSE "
            f"tid={self._tid(e)} node={e.node_id} "
            f"req={e.request_id} "
            f"status={e.status_code} "
            f"size={e.response_size_bytes}B "
            f"latency_ms={round(e.latency_ms, 1)}"
        )

    def _net_request_failed(self, e, w):
        return (
            f"{self._prefix(w)} [NET] FAILED "
            f"tid={self._tid(e)} node={e.node_id} "
            f"req={e.request_id} "
            f"type={e.error_type} status={e.status_code} "
            f"error={self._truncate(e.error_message)}"
        )

    def _net_retry_attempted(self, e, w):
        return (
            f"{self._prefix(w)} [NET] RETRY "
            f"tid={self._tid(e)} node={e.node_id} "
            f"req={e.request_id} "
            f"attempt={e.attempt} reason={e.reason}"
        )

    # =====================================================
    # EXPANSION TRACE HANDLERS
    # =====================================================

    def _exp_triggered(self, e, w):
        return (
            f"{self._prefix(w)} [EXP] TRIGGERED "
            f"tid={self._tid(e)} blueprint={e.blueprint_id} "
            f"reason={e.trigger_reason} "
            f"topic={self._truncate(e.target_topic, 60)}"
        )

    def _exp_prompt_built(self, e, w):
        return (
            f"{self._prefix(w)} [EXP] PROMPT_BUILT "
            f"tid={self._tid(e)} blueprint={e.blueprint_id} "
            f"style={e.style} n={e.num_descriptions} len={e.prompt_len}"
        )

    def _exp_seeds_generated(self, e, w):
        return (
            f"{self._prefix(w)} [EXP] SEEDS "
            f"tid={self._tid(e)} blueprint={e.blueprint_id} "
            f"count={e.seed_count} source={e.source}"
        )

    def _exp_candidate_scored(self, e, w):
        return (
            f"{self._prefix(w)} [EXP] CANDIDATE "
            f"tid={self._tid(e)} blueprint={e.blueprint_id} "
            f"sim={round(e.target_similarity, 4)} "
            f"seed={self._truncate(e.seed_preview, 60)}"
        )

    def _exp_candidate_pruned(self, e, w):
        return (
            f"{self._prefix(w)} [EXP] PRUNED "
            f"tid={self._tid(e)} blueprint={e.blueprint_id} "
            f"reason={e.reason} threshold={e.threshold} "
            f"seed={self._truncate(e.seed_preview, 60)}"
        )

    def _exp_space_bootstrapped(self, e, w):
        return (
            f"{self._prefix(w)} [EXP] BOOTSTRAPPED "
            f"tid={self._tid(e)} blueprint={e.blueprint_id} "
            f"vectors={e.vectors_added} "
            f"space_v={e.space_version} "
            f"duration_ms={round(e.duration_ms, 1)}"
        )