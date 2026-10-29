"""The crawl's stages, in one ordered registry.

Each entry names a stage, the ``pipelines.<name>`` setting its workers and
queue come from, and how to build it. ``Crawler`` builds, subscribes and
starts the stages in this order, so a new stage is one entry here plus its
builder (docs/adr/0002-crawl-composition-root.md).
"""

import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from config.paths import RuntimePaths
from config.runtime_config import RuntimeConfig
from infrastructure import NetworkClient
from infrastructure.call_budget import CallBudget
from models import Storage
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
    StopConditions,
    StoppingPipeline,
    StoragePipeline,
    TransformationPipeline,
)
from pipelines.contracts import Annotator, CrawlStage, RelevanceScorer

from .event_broker import EventBroker


@dataclass(frozen=True)
class StageInputs:
    """Everything a stage builder reads: the run's settings and the shared
    services the stages are given."""

    broker: EventBroker
    storage: Storage
    config: RuntimeConfig
    paths: RuntimePaths
    crawl_id: str
    # The blueprint as loaded from JSON (BootStrapper validates it first).
    blueprint: dict[str, Any]
    nlp_service: RelevanceScorer
    scoring_service: Annotator
    call_budget: CallBudget
    fetch_concurrency: int
    scoring_concurrency: int
    seed: int | None

    @property
    def stop_conditions(self) -> dict[str, Any]:
        conditions: dict[str, Any] = self.blueprint["stop_conditions"]
        return conditions

    @property
    def extraction(self) -> dict[str, Any] | None:
        extraction: dict[str, Any] | None = self.blueprint.get("extraction")
        return extraction

    @property
    def priority_strategy(self) -> str:
        return priority_strategy_name(self.blueprint, self.config)

    def rng(self, name: str) -> random.Random:
        """One independent stream per consumer, so adding a draw in one
        pipeline cannot shift another's sequence. Unseeded when no seed."""
        return random.Random(f"{self.seed}:{name}" if self.seed is not None else None)


def priority_strategy_name(blueprint: dict[str, Any], config: RuntimeConfig) -> str:
    """The blueprint's priority strategy, or the configured default."""
    name: str = blueprint["stop_conditions"].get(
        "priority_strategy", config.scoring_cascade.default_priority_strategy
    )
    return name


def _queue_size(bound: int | None) -> int:
    """A configured queue bound as asyncio's maxsize: None (no limit) is 0."""
    return bound or 0


Built = Mapping[str, CrawlStage]


def _logging(inputs: StageInputs, built: Built) -> CrawlStage:
    return LoggingPipeline(inputs.broker, inputs.crawl_id, log_root=inputs.paths.log_dir)


def _canonicalization(inputs: StageInputs, built: Built) -> CrawlStage:
    return CanonicalizationPipeline(
        inputs.crawl_id, inputs.broker, export_path=inputs.paths.export_dir
    )


def _debugging(inputs: StageInputs, built: Built) -> CrawlStage:
    settings = inputs.config.pipelines.debugging
    return DebuggingPipeline(
        inputs.broker,
        inputs.crawl_id,
        enabled=inputs.config.observability.debug_enabled,
        max_queue_size=_queue_size(settings.max_queue_size),
        max_concurrency=settings.workers,
        debug_root=inputs.paths.debug_dir,
    )


def _processing(inputs: StageInputs, built: Built) -> CrawlStage:
    settings = inputs.config.pipelines.processing
    return ProcessingPipeline(
        inputs.broker,
        inputs.extraction,
        max_concurrency=settings.workers,
        max_queue_size=_queue_size(settings.max_queue_size),
        link_context_length=inputs.config.nlp.link_context_length,
    )


def _requests(inputs: StageInputs, built: Built) -> CrawlStage:
    fetch = inputs.config.fetch
    return RequestsPipeline(
        inputs.broker,
        max_concurrency=inputs.fetch_concurrency,
        max_queue_size=_queue_size(inputs.config.pipelines.requests.max_queue_size),
        fetcher=NetworkClient(fetch.http_total_timeout, fetch.http_connect_timeout),
        min_delay=fetch.min_delay,
        user_agent=fetch.user_agent,
        respect_robots=fetch.respect_robots,
        rng=inputs.rng("requests"),
        jitter_max=fetch.jitter_max,
        robots_ttl=fetch.robots_ttl_seconds,
        backoff_start=fetch.backoff_start,
        max_backoff=fetch.backoff_max,
        backoff_growth=fetch.backoff_growth,
        backoff_success_decay=fetch.backoff_success_decay,
        backoff_failure_decay=fetch.backoff_failure_decay,
        extra_headers=fetch.extra_headers,
        accept=fetch.accept,
        accept_encoding=fetch.accept_encoding,
        accept_language=fetch.accept_language,
    )


def _retry(inputs: StageInputs, built: Built) -> CrawlStage:
    settings = inputs.config.pipelines.retry
    retries = inputs.config.retries
    return RetryProcessor(
        inputs.storage,
        inputs.broker,
        requests_pipeline=built["requests"],
        max_queue_size=_queue_size(settings.max_queue_size),
        max_concurrency=settings.workers,
        max_request_retries=retries.max_request_retries,
        max_scoring_retries=retries.max_scoring_retries,
        retry_base_delay=retries.base_delay,
        retry_growth=retries.growth,
        empty_score_demotion=retries.empty_score_demotion,
        fetch_retry_demotion=retries.fetch_retry_demotion,
    )


def _scoring(inputs: StageInputs, built: Built) -> CrawlStage:
    cascade = inputs.config.scoring_cascade
    return ScoringPipeline(
        inputs.scoring_service,
        inputs.nlp_service,
        inputs.broker,
        low_threshold=cascade.low_threshold,
        high_threshold=cascade.high_threshold,
        high_score_llm_fraction=cascade.high_score_llm_fraction,
        low_score_sample_fraction=cascade.low_score_sample_fraction,
        high_score_random_fraction=cascade.high_score_random_fraction,
        max_queue_size=_queue_size(inputs.config.pipelines.scoring.max_queue_size),
        percentile_bucketing=cascade.percentile_bucketing,
        low_percentile=cascade.low_percentile,
        high_percentile=cascade.high_percentile,
        percentile_min_links=cascade.percentile_min_links,
        max_llm_links=cascade.max_llm_links_per_node,
        llm_batch_size=cascade.llm_batch_size,
        max_concurrency=inputs.scoring_concurrency,
        rng=inputs.rng("scoring"),
        call_budget=inputs.call_budget,
    )


def _filtering(inputs: StageInputs, built: Built) -> CrawlStage:
    settings = inputs.config.pipelines.filtering
    return FilteringPipeline(
        inputs.broker,
        inputs.storage,
        max_concurrency=settings.workers,
        max_queue_size=_queue_size(settings.max_queue_size),
    )


def _priority(inputs: StageInputs, built: Built) -> CrawlStage:
    settings = inputs.config.pipelines.priority
    priority = inputs.config.priority
    strategy = inputs.priority_strategy
    return PriorityPipeline(
        inputs.storage,
        inputs.broker,
        nlp_bias=priority.nlp_bias,
        llm_bias=priority.llm_bias,
        strategy_name=strategy,
        max_queue_size=_queue_size(settings.max_queue_size),
        strategy_weights=getattr(priority, f"{strategy}_weights", None),
        max_concurrency=settings.workers,
    )


def _transformation(inputs: StageInputs, built: Built) -> CrawlStage:
    settings = inputs.config.pipelines.transformation
    return TransformationPipeline(
        inputs.broker,
        inputs.extraction,
        max_queue_size=_queue_size(settings.max_queue_size),
        max_concurrency=settings.workers,
    )


def _storage(inputs: StageInputs, built: Built) -> CrawlStage:
    settings = inputs.config.pipelines.storage
    return StoragePipeline(
        inputs.storage,
        inputs.broker,
        max_queue_size=_queue_size(settings.max_queue_size),
        max_concurrency=settings.workers,
        max_depth=inputs.stop_conditions["max_depth"],
    )


def _exporting(inputs: StageInputs, built: Built) -> CrawlStage:
    return ExportingPipeline(
        inputs.crawl_id,
        inputs.blueprint.get("blueprint_id"),
        inputs.blueprint,
        inputs.broker,
        db_path=inputs.paths.items_db,
        batch_size=inputs.config.export.batch_size,
    )


def _stopping(inputs: StageInputs, built: Built) -> CrawlStage:
    conditions = inputs.stop_conditions
    return StoppingPipeline(
        inputs.broker,
        StopConditions(
            max_nodes=conditions["max_nodes"],
            max_duration=conditions["max_duration"],
            no_progress_timeout=conditions["no_progress_timeout"],
            target_url=conditions["stop_url"],
        ),
        check_interval=inputs.config.run.stop_check_interval,
    )


@dataclass(frozen=True)
class StageSpec:
    key: str
    # The `pipelines.<setting>` its workers and queue bound come from; None
    # for stages without one.
    setting: str | None
    build: Callable[[StageInputs, Built], CrawlStage]


# Build, subscription and start order. A builder may use any stage above it.
STAGES: tuple[StageSpec, ...] = (
    StageSpec("logging", None, _logging),
    StageSpec("canon", None, _canonicalization),
    StageSpec("debug", "debugging", _debugging),
    StageSpec("processing", "processing", _processing),
    StageSpec("requests", "requests", _requests),
    StageSpec("retry", "retry", _retry),
    StageSpec("scoring", "scoring", _scoring),
    StageSpec("filtering", "filtering", _filtering),
    StageSpec("priority", "priority", _priority),
    StageSpec("transformation", "transformation", _transformation),
    StageSpec("storage", "storage", _storage),
    StageSpec("exporting", None, _exporting),
    StageSpec("stopping", None, _stopping),
)


def build_stages(inputs: StageInputs) -> dict[str, CrawlStage]:
    """Every stage, keyed and ordered as in `STAGES`."""
    built: dict[str, CrawlStage] = {}
    for spec in STAGES:
        built[spec.key] = spec.build(inputs, built)
    return built
