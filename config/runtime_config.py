"""
RuntimeConfig
=============
A validated, introspectable schema over the constants in config.py's
"SCORING CASCADE" / "NLP EMBEDDINGS" / "EXPORT" sections -- the tunable
surface a researcher needs visibility into to answer "what assumptions is
this crawl operating under?".

Why this exists
----------------
`routes/blueprint_schema.py` already solved this exact problem for
blueprints: a Pydantic model as the single source of truth, with its
JSON schema exported for the frontend rather than hand-duplicated. That
model's own docstring documents three past incidents of drift between
independently-maintained copies of the same shape. `routes/blueprint_ui_schema.json`
took a further step -- a hand-written ui-hints JSON schema for
form-rendering -- but was never wired to anything on either side (dead
file). This module applies the
working half of that pattern (a Pydantic model, `Field(...)` for both
validation AND ui hints, `.model_json_schema()` generated rather than
hand-copied) to the runtime tuning surface described in the engineering
philosophy brief.

Scope
-----
`Crawler` takes a RuntimeConfig (defaulting to `default_runtime_config()`)
and reads these thresholds and batching sizes from it, so a run can carry
its own overrides. `GET /config` reports the defaults. The percentile
bucketing constants and the politeness settings stay in config.py.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

import config as _config
from infrastructure.llm_handler import LlmHandler
from models.prompts import SCORING_RULES, SCORING_SYSTEM_PROMPT, STRATEGIES
from priority.strategy import DEFAULT_WEIGHTS, WEIGHT_KEYS


def _f(default: Any, description: str, section: str, widget: str = "number", *,
       unit: str | None = None, apply: str = "next_run", advanced: bool = False,
       options: list | None = None, step: float | None = None, pair: str | None = None,
       active_when: tuple[str, Any] | None = None, **constraints: Any):
    """Field with the ui hints the settings page renders from.

    ``apply`` is ``next_run`` (read at Crawler construction) or ``live``
    (read per loop iteration through the run's LiveSettings). ``step`` is the
    increment a number control moves by (seconds default to 0.1); ``pair``
    names the sibling field drawn on the same two-thumb range, the earlier
    field being the lower bound; ``active_when`` is ``(sibling, value)`` and
    dims the control while that sibling holds another value."""
    extra: dict[str, Any] = {"ui_section": section, "ui_widget": widget,
                             "ui_apply": apply, "ui_advanced": advanced}
    if unit:
        extra["ui_unit"] = unit
    if step is None and unit == "s":
        step = 0.1
    if step is not None:
        extra["ui_step"] = step
    if pair:
        extra["ui_pair"] = pair
    if active_when:
        extra["ui_active_when"] = {"field": active_when[0], "value": active_when[1]}
    if options:
        extra["ui_options"] = options
    if isinstance(default, (dict, list)):
        return Field(default_factory=lambda: type(default)(default), description=description,
                     json_schema_extra=extra, **constraints)
    return Field(default=default, description=description, json_schema_extra=extra, **constraints)


class ScoringCascadeConfig(BaseModel):
    """The two-stage NLP -> LLM relevance cascade's tunable thresholds and
    sampling fractions (report section 0.13, "Evaluation multi-etapes")."""

    percentile_bucketing: bool = _f(
        _config.NLP_PERCENTILE_BUCKETING,
        "Bucket links by per-node score percentile instead of the absolute thresholds.",
        "Scoring cascade", "segmented",
        options=[{"label": "Fixed score cut-offs", "value": False},
                 {"label": "Per-page percentiles", "value": True}])

    low_threshold: float = Field(
        default=_config.NLP_LOW_SCORE_THRESHOLD, ge=0.0, le=1.0,
        description="NLP similarity score below which a link is considered low-confidence.",
        json_schema_extra={"ui_section": "Scoring cascade", "ui_widget": "range", "ui_step": 0.01,
                           "ui_pair": "high_threshold",
                           "ui_active_when": {"field": "percentile_bucketing", "value": False}},
    )
    high_threshold: float = Field(
        default=_config.NLP_HIGH_SCORE_THRESHOLD, ge=0.0, le=1.0,
        description="NLP similarity score above which a link is considered high-confidence.",
        json_schema_extra={"ui_section": "Scoring cascade", "ui_widget": "range", "ui_step": 0.01,
                           "ui_pair": "low_threshold",
                           "ui_active_when": {"field": "percentile_bucketing", "value": False}},
    )
    high_score_llm_fraction: float = Field(
        default=_config.HIGH_SCORE_LLM_FRACTION, ge=0.0, le=1.0,
        description=(
            "Fraction of the high-confidence bucket still sent to the LLM rather than "
            "trusted outright -- this is the cascade's cost-saving lever."
        ),
        json_schema_extra={"ui_section": "Scoring cascade", "ui_widget": "slider"},
    )
    high_score_random_fraction: float = Field(
        default=_config.HIGH_SCORE_RANDOM_FRACTION, ge=0.0, le=1.0,
        description="Of the LLM-bound slice of the high bucket, the fraction chosen at random rather than by top NLP rank (bias correction).",
        json_schema_extra={"ui_section": "Scoring cascade", "ui_widget": "slider"},
    )
    low_score_sample_fraction: float = Field(
        default=_config.LOW_SCORE_SAMPLE_FRACTION, ge=0.0, le=1.0,
        description="Fraction of the low-confidence bucket kept anyway, for exploration, instead of dropped outright.",
        json_schema_extra={"ui_section": "Scoring cascade", "ui_widget": "slider"},
    )
    default_priority_strategy: str = Field(
        default=_config.DEFAULT_PRIORITY_STRATEGY,
        description="Priority strategy used when a blueprint doesn't specify one.",
        json_schema_extra={"ui_section": "Scoring cascade", "ui_widget": "select",
                            "ui_options": ["aggressive", "balanced", "exploration"]},
    )

    low_percentile: float = _f(
        _config.NLP_LOW_PERCENTILE, "Percentile below which a link falls in the low bucket.",
        "Scoring cascade", "range", unit="%", step=1, pair="high_percentile",
        active_when=("percentile_bucketing", True), ge=0.0, le=100.0)
    high_percentile: float = _f(
        _config.NLP_HIGH_PERCENTILE, "Percentile above which a link falls in the high bucket.",
        "Scoring cascade", "range", unit="%", step=1, pair="low_percentile",
        active_when=("percentile_bucketing", True), ge=0.0, le=100.0)
    percentile_min_links: int = _f(
        _config.PERCENTILE_MIN_LINKS,
        "Fewer links than this on a page fall back to the absolute thresholds.",
        "Scoring cascade", ge=1)
    max_llm_links_per_node: int = _f(
        _config.MAX_LLM_LINKS_PER_NODE, "Hard cap on links sent to the LLM for one page.",
        "Scoring cascade", ge=1)
    llm_batch_size: int | None = _f(
        None, "Links per LLM call; empty sends all of a page's links in one call.",
        "Scoring cascade", advanced=True, ge=1)

    @model_validator(mode="after")
    def _percentiles_ordered(self) -> "ScoringCascadeConfig":
        if self.low_percentile >= self.high_percentile:
            raise ValueError(
                f"low_percentile ({self.low_percentile}) must be less than "
                f"high_percentile ({self.high_percentile})"
            )
        return self

    @model_validator(mode="after")
    def _thresholds_ordered(self) -> "ScoringCascadeConfig":
        if self.low_threshold >= self.high_threshold:
            raise ValueError(
                f"low_threshold ({self.low_threshold}) must be less than "
                f"high_threshold ({self.high_threshold})"
            )
        return self


class EmbeddingConfig(BaseModel):
    """Semantic-space embedding backend (nlp/vector_space.py, nlp/space_updater.py)."""

    backend: str = Field(
        default=_config.EMBEDDING_BACKEND,
        description="Embedding backend used to build the crawl's semantic space.",
        json_schema_extra={"ui_section": "Embeddings", "ui_widget": "select",
                            "ui_options": ["sentence_transformers"]},
    )
    model_name: str = Field(
        default=_config.EMBEDDING_MODEL,
        description="Model identifier passed to the embedding backend.",
        json_schema_extra={"ui_section": "Embeddings", "ui_widget": "text"},
    )
    flush_interval_seconds: float = Field(
        default=_config.FLUSH_INTERVAL_SECONDS, gt=0,
        description="Maximum time between semantic-space growth flushes.",
        json_schema_extra={"ui_section": "Embeddings", "ui_widget": "number"},
    )
    flush_threshold: int = Field(
        default=_config.FLUSH_THRESHOLD, gt=0,
        description="Buffered scored-link count that triggers an early flush.",
        json_schema_extra={"ui_section": "Embeddings", "ui_widget": "number"},
    )
    buffer_max_size: int = Field(
        default=_config.BUFFER_MAX_SIZE, gt=0,
        description="Upper bound on the flush buffer before backpressure applies.",
        json_schema_extra={"ui_section": "Embeddings", "ui_widget": "number"},
    )


class ExportConfig(BaseModel):
    """Item export / persistence batching (pipelines/exporting_pipeline.py)."""

    batch_size: int = Field(
        default=_config.EXPORT_BATCH_SIZE, gt=0,
        description="Number of transformed items grouped into one export batch.",
        json_schema_extra={"ui_section": "Export", "ui_widget": "number"},
    )


class FetchConfig(BaseModel):
    """Page fetching: politeness, backoff, timeouts and request headers
    (pipelines/requests_pipeline.py, infrastructure/network_client.py)."""

    min_delay: float = _f(1.0, "Minimum seconds between two requests (global, all workers).",
                          "Fetch", unit="s", apply="live", ge=0.0)
    jitter_max: float = _f(0.2, "Random 0..N seconds added to every request delay.",
                           "Fetch", unit="s", apply="live", ge=0.0)
    backoff_start: float = _f(1.0, "First backoff delay after a 429 response.",
                              "Fetch", unit="s", ge=0.0)
    backoff_max: float = _f(10.0, "Upper bound for the shared 429 backoff.",
                            "Fetch", unit="s", apply="live", ge=0.0)
    backoff_growth: float = _f(2.0, "Backoff multiplier on each further 429.",
                               "Fetch", ge=1.0)
    backoff_success_decay: float = _f(0.5, "Backoff multiplier after a successful fetch.",
                                      "Fetch", ge=0.0, le=1.0)
    backoff_failure_decay: float = _f(0.5, "Backoff multiplier after a non-429 failure.",
                                      "Fetch", ge=0.0, le=1.0)
    http_total_timeout: float = _f(30.0, "Whole-request timeout for page fetches and LLM calls.",
                                   "Fetch", unit="s", gt=0.0)
    http_connect_timeout: float = _f(10.0, "Connection-establishment timeout.",
                                     "Fetch", unit="s", gt=0.0)
    respect_robots: bool = _f(_config.RESPECT_ROBOTS, "Honor robots.txt before fetching.",
                              "Fetch", "toggle")
    robots_ttl_seconds: float = _f(0.0, "Seconds a parsed robots.txt is kept; 0 keeps it for the whole crawl.",
                                   "Fetch", unit="s", advanced=True, ge=0.0)
    user_agent: str = _f(_config.USER_AGENT, "User-Agent header sent with every request.",
                         "Fetch", "text")
    accept: str = _f("text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                     "Accept header.", "Fetch", "text", advanced=True)
    accept_encoding: str = _f("gzip, deflate", "Accept-Encoding header.",
                              "Fetch", "text", advanced=True)
    accept_language: str = _f("", "Accept-Language header; empty omits it.",
                              "Fetch", "text", advanced=True)
    extra_headers: dict[str, str] = _f(
        {}, "Additional request headers; override the ones above on a name clash.",
        "Fetch", "headers")

    @model_validator(mode="after")
    def _ordered(self) -> "FetchConfig":
        if self.backoff_start > self.backoff_max:
            raise ValueError("backoff_start must not exceed backoff_max")
        if self.http_connect_timeout > self.http_total_timeout:
            raise ValueError("http_connect_timeout must not exceed http_total_timeout")
        return self


class PipelineSettings(BaseModel):
    """Worker count and queue bound of one pipeline."""

    workers: int = Field(default=1, ge=1, le=64, description="Concurrent worker loops.",
                         json_schema_extra={"ui_apply": "live", "ui_widget": "stepper"})
    max_queue_size: int | None = Field(
        default=None, ge=1, description="Queue bound; empty is unbounded.",
        json_schema_extra={"ui_widget": "limit", "ui_step": 100})

    @field_validator("max_queue_size", mode="before")
    @classmethod
    def _legacy_zero_is_unbounded(cls, v: Any) -> Any:
        """Settings saved before the bound became nullable stored 0 for 'no limit'."""
        return None if v == 0 else v


def _pl(workers: int) -> Any:
    return Field(default_factory=lambda: PipelineSettings(workers=workers))


class PipelinesConfig(BaseModel):
    """Per-pipeline parallelism (core/crawler.py:_build_pipelines). Logging
    and canonicalization stay single-worker so output order is preserved."""

    processing: PipelineSettings = _pl(1)
    requests: PipelineSettings = _pl(4)
    scoring: PipelineSettings = _pl(1)
    storage: PipelineSettings = _pl(1)
    filtering: PipelineSettings = _pl(10)
    priority: PipelineSettings = _pl(10)
    transformation: PipelineSettings = _pl(3)
    debugging: PipelineSettings = _pl(2)
    retry: PipelineSettings = _pl(1)


class RetryConfig(BaseModel):
    """Retry policy (pipelines/retry_processor.py)."""

    max_request_retries: int = _f(3, "Requeues of a node after failed fetches.",
                                  "Retries", apply="live", ge=0)
    max_scoring_retries: int = _f(3, "Reschedules of a node after failed scoring.",
                                  "Retries", apply="live", ge=0)
    base_delay: float = _f(2.0, "First retry delay; grows by `growth` each attempt.",
                           "Retries", unit="s", ge=0.0)
    growth: float = _f(2.0, "Retry delay multiplier per attempt.", "Retries", ge=1.0)
    empty_score_demotion: float = _f(5, "Priority removed from a node whose LLM result was empty.",
                                     "Retries", ge=0)
    fetch_retry_demotion: float = _f(2, "Priority removed from a node on each fetch retry.",
                                     "Retries", ge=0)


class UrlConfig(BaseModel):
    """Node identity rules (utils/html_utils.py:normalize_url). Changing them
    changes which links count as the same page."""

    strip_fragment: bool = _f(True, "Treat /page#a and /page as one page.",
                              "URLs", "toggle", advanced=True)
    strip_trailing_slash: bool = _f(True, "Treat /page/ and /page as one page.",
                                    "URLs", "toggle", advanced=True)


def _weights(name: str) -> Any:
    return _f(dict(DEFAULT_WEIGHTS[name]),
              f"Feature weights of the '{name}' priority strategy; depth_penalty is "
              "subtracted per level of depth.", "Priority", "weights", advanced=True)


class PriorityConfig(BaseModel):
    """Mix of NLP and LLM scores in a link's priority (priority_pipeline.py)."""

    nlp_bias: float = _f(60, "Weight of the NLP score (normalized with llm_bias).",
                         "Priority", "slider", ge=0)
    llm_bias: float = _f(40, "Weight of the LLM score (normalized with nlp_bias).",
                         "Priority", "slider", ge=0)

    aggressive_weights: dict[str, float] = _weights("aggressive")
    balanced_weights: dict[str, float] = _weights("balanced")
    exploration_weights: dict[str, float] = _weights("exploration")

    @model_validator(mode="after")
    def _known_weights(self) -> "PriorityConfig":
        for name in DEFAULT_WEIGHTS:
            unknown = set(getattr(self, f"{name}_weights")) - WEIGHT_KEYS
            if unknown:
                raise ValueError(
                    f"{name}_weights: unknown feature(s) {sorted(unknown)}; "
                    f"allowed: {sorted(WEIGHT_KEYS)}"
                )
        return self

    @model_validator(mode="after")
    def _positive_sum(self) -> "PriorityConfig":
        if self.nlp_bias + self.llm_bias <= 0:
            raise ValueError("nlp_bias + llm_bias must be positive")
        return self


class NlpConfig(BaseModel):
    """NLP composite score (services/nlp_service.py)."""

    composite_weights: dict[str, float] = _f(
        dict(_config.NLP_COMPOSITE_WEIGHTS),
        "Feature weights of the composite NLP score (negative subtracts).",
        "NLP", "weights")
    target_top_k: int = _f(2, "Nearest target-basis vectors averaged into target similarity.",
                           "NLP", ge=1)
    cluster_eps: float = _f(0.3, "DBSCAN cosine radius used to find clusters in the semantic space.",
                            "NLP", advanced=True, gt=0.0)
    cluster_min_samples: int = _f(2, "DBSCAN minimum points per cluster.",
                                  "NLP", advanced=True, ge=1)
    link_context_length: int = _f(100, "Characters of surrounding text kept as a link's context.",
                                  "NLP", unit="chars", ge=1)


class LlmConfig(BaseModel):
    """Request parameters shared by every LLM provider call."""

    max_tokens: int | None = _f(None, "Completion token cap; empty uses the provider default.",
                                "LLM", ge=1)
    temperature: float | None = _f(None, "Sampling temperature; empty uses the provider default.",
                                   "LLM", ge=0.0, le=2.0)
    key_cooldown_seconds: float = _f(0.0, "Minimum gap before the same API key is reused.",
                                     "LLM", unit="s", ge=0.0)


class ObservabilityConfig(BaseModel):
    debug_enabled: bool = _f(_config.DEBUG, "Write the per-crawl debug trace file.",
                             "Observability", "toggle")
    ui_port: int = _f(8765, "Websocket port the live graph connects to.",
                      "Observability", ge=1, le=65535)
    snapshot_max_candidates: int = _f(4000, "Scoring decisions kept for the live view.",
                                      "Observability", advanced=True, ge=1)
    snapshot_max_errors: int = _f(1000, "Crawl errors kept for the live view.",
                                  "Observability", advanced=True, ge=1)


class PromptsConfig(BaseModel):
    """Wording of the scoring prompt (models/prompts.py). The output format
    and JSON constraints are fixed because the response parser depends on
    them."""

    scoring_system: str = _f(SCORING_SYSTEM_PROMPT, "System prompt of the link-scoring LLM call.",
                             "Prompts", "textarea", min_length=1)
    scoring_rules: str = _f(SCORING_RULES, "RULES block of the scoring prompt.",
                            "Prompts", "textarea", min_length=1)
    strategy_contexts: dict[str, str] = _f(
        {k: v["context"] for k, v in STRATEGIES.items()},
        "Wording that biases the scoring LLM, per scoring strategy.", "Prompts", "stringmap")

    @model_validator(mode="after")
    def _known_strategies(self) -> "PromptsConfig":
        unknown = set(self.strategy_contexts) - set(STRATEGIES)
        if unknown:
            raise ValueError(f"unknown scoring strateg(ies): {sorted(unknown)}")
        return self


class ProvidersConfig(BaseModel):
    """Request URL per LLM provider (infrastructure/llm_handler.py). Point a
    provider at any compatible server; Gemini takes a base URL."""

    endpoints: dict[str, str] = _f(
        dict(LlmHandler.DEFAULT_ENDPOINTS),
        "Request URL used for each provider.", "Providers", "stringmap")

    @model_validator(mode="after")
    def _valid(self) -> "ProvidersConfig":
        for name, url in self.endpoints.items():
            if name not in LlmHandler.DEFAULT_ENDPOINTS:
                raise ValueError(f"unknown provider '{name}'")
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"{name}: endpoint must start with http:// or https://")
        return self


class RunConfig(BaseModel):
    seed: int | None = _f(None, "Seed for every random stream; empty is unseeded.", "Run")
    stop_check_interval: float = _f(0.1, "Seconds between stop-condition checks on a quiet crawl.",
                                    "Run", unit="s", advanced=True, gt=0.0)
    shutdown_grace: float = _f(5.0, "Seconds the other tasks get to finish once a crawl stops.",
                               "Run", unit="s", advanced=True, ge=0.0)


SECTION_GUIDE = [
    ("Scoring cascade", "Decides which links the cheap NLP score settles and which are worth an LLM call."),
    ("Fetch", "How fast and how politely pages are requested, and how the crawler backs off."),
    ("Priority", "How the score, depth and strategy weights order the queue of pages still to visit."),
    ("Prompts", "The instructions the LLM receives when it judges a batch of links."),
    ("Providers", "Which LLM service answers, and which models it may use."),
    ("Pipelines", "How many workers each stage runs and how long its queue may grow."),
    ("Retries", "What happens to a page whose fetch or scoring failed."),
    ("Embeddings", "The model that turns text into vectors for similarity scoring."),
    ("NLP", "How link text and context are turned into a similarity score."),
    ("LLM", "Request limits for the language model calls."),
    ("URLs", "Which links count as the same page."),
    ("Export", "What a finished crawl writes to disk."),
    ("Observability", "Logging, debugging and the live graph connection."),
    ("Run", "Seeds and shutdown timing of a crawl."),
]


class RuntimeConfig(BaseModel):
    """Top-level runtime configuration: everything a researcher would want
    to see before trusting a crawl's results, beyond the per-run blueprint
    (target topic, seeds, extraction schema) already covered by
    routes/blueprint_schema.py."""

    scoring_cascade: ScoringCascadeConfig = Field(default_factory=ScoringCascadeConfig)
    embeddings: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)
    fetch: FetchConfig = Field(default_factory=FetchConfig)
    pipelines: PipelinesConfig = Field(default_factory=PipelinesConfig)
    retries: RetryConfig = Field(default_factory=RetryConfig)
    priority: PriorityConfig = Field(default_factory=PriorityConfig)
    url: UrlConfig = Field(default_factory=UrlConfig)
    nlp: NlpConfig = Field(default_factory=NlpConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    run: RunConfig = Field(default_factory=RunConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)

    model_config = ConfigDict(json_schema_extra={
        "ui_sections": [{"name": n, "help": h} for n, h in SECTION_GUIDE]})


def default_runtime_config() -> RuntimeConfig:
    """The config currently in effect, read from config.py's constants."""
    return RuntimeConfig()
