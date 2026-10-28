"""
RuntimeConfig
=============
A validated, introspectable schema over the constants in config.py's
"SCORING CASCADE" / "NLP EMBEDDINGS" / "EXPORT" sections -- the tunable
surface a researcher needs visibility into to answer "what assumptions is
this crawl operating under?".

Why this exists
----------------
`config/blueprint_schema.py` already solved this exact problem for
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

Content rule
------------
Every field a user can see (not ``advanced``) carries an ``effect`` line:
one plain sentence on what changes when the value is raised or changed.
``tests/test_schema_content.py`` enforces it on the served schema.
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
       active_when: tuple[str, Any] | None = None, effect: str | None = None,
       **constraints: Any):
    """Field with the ui hints the settings page renders from.

    ``apply`` is ``next_run`` (read at Crawler construction) or ``live``
    (read per loop iteration through the run's LiveSettings). ``step`` is the
    increment a number control moves by (seconds default to 0.1); ``pair``
    names the sibling field drawn on the same two-thumb range, the earlier
    field being the lower bound; ``active_when`` is ``(sibling, value)`` and
    dims the control while that sibling holds another value; ``effect`` is
    one plain sentence on what changes when the value is raised or changed."""
    extra: dict[str, Any] = {"ui_section": section, "ui_widget": widget,
                             "ui_apply": apply, "ui_advanced": advanced}
    if unit is not None:
        # "" marks a number that is deliberately unitless (a count or a multiplier).
        extra["ui_unit"] = unit
    if effect:
        extra["ui_effect"] = effect
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
                 {"label": "Per-page percentiles", "value": True}],
        effect="Percentiles judge each link against its own page; fixed cut-offs judge every link against the same scale.")

    low_threshold: float = _f(
        _config.NLP_LOW_SCORE_THRESHOLD, "NLP similarity score below which a link is considered low-confidence.",
        "Scoring cascade", "range", unit="", step=0.01, pair="high_threshold",
        active_when=("percentile_bucketing", False), ge=0.0, le=1.0,
        effect="Raising it moves more links into the low-confidence bucket, where most are dropped.")
    high_threshold: float = _f(
        _config.NLP_HIGH_SCORE_THRESHOLD, "NLP similarity score above which a link is considered high-confidence.",
        "Scoring cascade", "range", unit="", step=0.01, pair="low_threshold",
        active_when=("percentile_bucketing", False), ge=0.0, le=1.0,
        effect="Lowering it moves more links into the high-confidence bucket, which the LLM judges less often.")
    high_score_llm_fraction: float = _f(
        _config.HIGH_SCORE_LLM_FRACTION,
        "Fraction of the high-confidence bucket still sent to the LLM rather than trusted outright.",
        "Scoring cascade", "slider", unit="", ge=0.0, le=1.0,
        effect="Lowering it saves LLM calls; raising it checks more of the high bucket with the LLM.")
    high_score_random_fraction: float = _f(
        _config.HIGH_SCORE_RANDOM_FRACTION,
        "Of the LLM-bound slice of the high bucket, the fraction chosen at random rather than by top NLP rank.",
        "Scoring cascade", "slider", unit="", ge=0.0, le=1.0,
        effect="Raising it checks more random high-bucket links, which corrects bias from always taking the top-ranked ones.")
    low_score_sample_fraction: float = _f(
        _config.LOW_SCORE_SAMPLE_FRACTION,
        "Fraction of the low-confidence bucket kept anyway, for exploration, instead of dropped outright.",
        "Scoring cascade", "slider", unit="", ge=0.0, le=1.0,
        effect="Raising it keeps more doubtful links for the LLM, so the crawl explores more and spends more calls.")
    default_priority_strategy: str = _f(
        _config.DEFAULT_PRIORITY_STRATEGY,
        "Priority strategy used when a blueprint doesn't specify one.",
        "Priority", "select", options=["aggressive", "balanced", "exploration"],
        effect="Sets how the queue is ordered when a blueprint does not pick a strategy. Chosen with the cards above the weights.")

    low_percentile: float = _f(
        _config.NLP_LOW_PERCENTILE, "Percentile below which a link falls in the low bucket.",
        "Scoring cascade", "range", unit="%", step=1, pair="high_percentile",
        active_when=("percentile_bucketing", True), ge=0.0, le=100.0,
        effect="Raising it sends fewer links to the low bucket, so fewer are dropped outright.")
    high_percentile: float = _f(
        _config.NLP_HIGH_PERCENTILE, "Percentile above which a link falls in the high bucket.",
        "Scoring cascade", "range", unit="%", step=1, pair="low_percentile",
        active_when=("percentile_bucketing", True), ge=0.0, le=100.0,
        effect="Lowering it sends more links to the high bucket, which the LLM judges less often.")
    percentile_min_links: int = _f(
        _config.PERCENTILE_MIN_LINKS,
        "Fewer links than this on a page fall back to the absolute thresholds.",
        "Scoring cascade", unit="links", ge=1,
        effect="Raising it makes small pages use the fixed cut-offs instead of percentiles.")
    max_llm_links_per_node: int = _f(
        _config.MAX_LLM_LINKS_PER_NODE, "Hard cap on links sent to the LLM for one page.",
        "Scoring cascade", unit="links", ge=1,
        effect="Caps the LLM work of any single page; links above the cap are not judged by the LLM.")
    llm_batch_size: int | None = _f(
        None, "Links per LLM call; empty sends all of a page's links in one call.",
        "Scoring cascade", advanced=True, unit="links", ge=1,
        effect="Smaller batches make more calls with shorter prompts; larger batches make fewer calls.")

    @model_validator(mode="after")
    def _percentiles_ordered(self) -> "ScoringCascadeConfig":
        if self.low_percentile >= self.high_percentile:
            raise ValueError(
                "The low percentile must be below the high percentile "
                f"(now {self.low_percentile:g} and {self.high_percentile:g})."
            )
        return self

    @model_validator(mode="after")
    def _thresholds_ordered(self) -> "ScoringCascadeConfig":
        if self.low_threshold >= self.high_threshold:
            raise ValueError(
                "The low score cut-off must be below the high score cut-off "
                f"(now {self.low_threshold:g} and {self.high_threshold:g})."
            )
        return self


class EmbeddingConfig(BaseModel):
    """Semantic-space embedding backend (nlp/vector_space.py, nlp/space_updater.py)."""

    backend: str = _f(
        _config.EMBEDDING_BACKEND, "Embedding backend used to build the crawl's semantic space.",
        "Embeddings", "select", options=["sentence_transformers"],
        effect="Switching backend changes every similarity score the crawl computes.")
    model_name: str = _f(
        _config.EMBEDDING_MODEL, "Model identifier passed to the embedding backend.",
        "Embeddings", "text",
        effect="A different model gives different vectors, so similarity scores shift.")
    flush_interval_seconds: float = _f(
        _config.FLUSH_INTERVAL_SECONDS, "Maximum time between semantic-space growth flushes.",
        "Embeddings", unit="s", gt=0,
        effect="Longer waits let more scored links accumulate before the space learns from them; shorter updates it more often.")
    flush_threshold: int = _f(
        _config.FLUSH_THRESHOLD, "Buffered scored-link count that triggers an early flush.",
        "Embeddings", unit="links", gt=0,
        effect="Lower flushes sooner when many links arrive quickly; higher lets the buffer grow between flushes.")
    buffer_max_size: int = _f(
        _config.BUFFER_MAX_SIZE, "Upper bound on the flush buffer before backpressure applies.",
        "Embeddings", unit="links", gt=0,
        effect="When the buffer is full, the stage that feeds it waits instead of queuing more links.")


class ExportConfig(BaseModel):
    """Item export / persistence batching (pipelines/exporting_pipeline.py)."""

    batch_size: int = _f(
        _config.EXPORT_BATCH_SIZE, "Number of transformed items grouped into one export batch.",
        "Export", unit="items", gt=0,
        effect="Larger batches mean fewer writes; smaller batches write more often.")


class FetchConfig(BaseModel):
    """Page fetching: politeness, backoff, timeouts and request headers
    (pipelines/requests_pipeline.py, infrastructure/network_client.py)."""

    min_delay: float = _f(
        1.0, "Minimum seconds between two requests (global, all workers).",
        "Fetch", unit="s", apply="live", ge=0.0,
        effect="The main politeness control: raising it slows every request the crawler makes, across all workers.")
    jitter_max: float = _f(
        0.2, "Random 0..N seconds added to every request delay.",
        "Fetch", unit="s", apply="live", ge=0.0,
        effect="Adds a random pause up to this length to each request, so requests do not arrive on a fixed beat.")
    backoff_start: float = _f(
        1.0, "First backoff delay after a 429 response.",
        "Fetch", unit="s", ge=0.0,
        effect="Sets how long the crawler waits after the first 429 (too many requests) response from a site.")
    backoff_max: float = _f(
        10.0, "Upper bound for the shared 429 backoff.",
        "Fetch", unit="s", apply="live", ge=0.0,
        effect="Caps how long the shared backoff can grow after repeated 429 responses.")
    backoff_growth: float = _f(
        2.0, "Backoff multiplier on each further 429.",
        "Fetch", unit="", ge=1.0,
        effect="Each further 429 multiplies the backoff by this, so higher values back off faster.")
    backoff_success_decay: float = _f(
        0.5, "Backoff multiplier after a successful fetch.",
        "Fetch", unit="", ge=0.0, le=1.0,
        effect="Each successful fetch multiplies the backoff by this; 1 keeps it unchanged, lower values restore speed faster.")
    backoff_failure_decay: float = _f(
        0.5, "Backoff multiplier after a non-429 failure.",
        "Fetch", unit="", ge=0.0, le=1.0,
        effect="A failure that is not a 429 multiplies the backoff by this; lower values let a struggling site recover speed faster.")
    http_total_timeout: float = _f(
        30.0, "Whole-request timeout for page fetches and LLM calls.",
        "Fetch", unit="s", gt=0.0,
        effect="A page or LLM reply that takes longer than this counts as a failed request and is retried.")
    http_connect_timeout: float = _f(
        10.0, "Connection-establishment timeout.",
        "Fetch", unit="s", gt=0.0,
        effect="A host that does not accept the connection within this time counts as a failed request.")
    respect_robots: bool = _f(
        _config.RESPECT_ROBOTS, "Honor robots.txt before fetching.",
        "Fetch", "toggle",
        effect="On: pages a site disallows in robots.txt are skipped. Off: they are fetched anyway.")
    robots_ttl_seconds: float = _f(
        0.0, "Seconds a parsed robots.txt is kept; 0 keeps it for the whole crawl.",
        "Fetch", unit="s", advanced=True, ge=0.0,
        effect="Longer keeps robots.txt rules longer before the file is fetched again.")
    user_agent: str = _f(
        _config.USER_AGENT, "User-Agent header sent with every request.",
        "Fetch", "text",
        effect="Sites read this name on every request, and some block agents they do not know; changing it changes how the crawler identifies itself.")
    accept: str = _f(
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept header.", "Fetch", "text", advanced=True,
        effect="Tells servers which content types to send; a different list can change which version of a page comes back.")
    accept_encoding: str = _f(
        "gzip, deflate", "Accept-Encoding header.", "Fetch", "text", advanced=True,
        effect="Tells servers which compressions the crawler can read; removing one makes servers send pages uncompressed or with another method.")
    accept_language: str = _f(
        "", "Accept-Language header; empty omits it.", "Fetch", "text", advanced=True,
        effect="Asks sites for pages in this language when they offer several; empty lets each site choose.")
    extra_headers: dict[str, str] = _f(
        {}, "Additional request headers; override the ones above on a name clash.",
        "Fetch", "headers",
        effect="Each header is sent on every request and replaces a default header of the same name.")

    @model_validator(mode="after")
    def _ordered(self) -> "FetchConfig":
        if self.backoff_start > self.backoff_max:
            raise ValueError(
                "The first backoff must not be longer than the backoff maximum "
                f"(now {self.backoff_start:g} s and {self.backoff_max:g} s).")
        if self.http_connect_timeout > self.http_total_timeout:
            raise ValueError(
                "The connection timeout must not be longer than the whole-request timeout "
                f"(now {self.http_connect_timeout:g} s and {self.http_total_timeout:g} s).")
        return self


class PipelineSettings(BaseModel):
    """Worker count and queue bound of one pipeline."""

    workers: int = _f(
        1, "Concurrent worker loops.", "Pipelines", "stepper", unit="", apply="live", ge=1, le=64,
        effect="More workers drain this stage's queue faster, so the crawl moves faster, but more work is held in memory at once and more calls go out in parallel.")
    max_queue_size: int | None = _f(
        None, "Queue bound; empty is unbounded.", "Pipelines", "limit", unit="items", step=100, ge=1,
        effect="Caps how much work waits for this stage. Once it is full, the stage before it waits, so memory stays flat and the crawl slows. Empty lets memory grow without limit.")

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

    max_request_retries: int = _f(
        3, "Requeues of a node after failed fetches.",
        "Retries", apply="live", unit="", ge=0,
        effect="A page that fails to fetch is requeued this many times before the crawler gives up on it. Each retry sends another request to the site, so a failing site gets more load.")
    max_scoring_retries: int = _f(
        3, "Reschedules of a node after failed scoring.",
        "Retries", apply="live", unit="", ge=0,
        effect="A page whose scoring fails is rescheduled this many times before the crawler gives up on it. Each reschedule sends the LLM call again, so it spends LLM calls and budget.")
    base_delay: float = _f(
        2.0, "First retry delay; grows by `growth` each attempt.",
        "Retries", unit="s", ge=0.0,
        effect="The wait before the first retry; later retries wait longer by the growth multiplier.")
    growth: float = _f(
        2.0, "Retry delay multiplier per attempt.", "Retries", unit="", ge=1.0,
        effect="Multiplies the retry wait on each attempt; 1 waits the same time every attempt.")
    empty_score_demotion: float = _f(
        5, "Places a page later in the queue when its LLM result was empty.",
        "Retries", unit="", ge=0,
        effect="Lowers the page's place in the queue by this many priority points when its LLM result came back empty, so it is crawled later.")
    fetch_retry_demotion: float = _f(
        2, "Places a page later in the queue on each fetch retry.",
        "Retries", unit="", ge=0,
        effect="Lowers the page's place in the queue by this many priority points on every fetch retry, so failing pages are tried later.")


class UrlConfig(BaseModel):
    """Node identity rules (utils/html_utils.py:normalize_url). Changing them
    changes which links count as the same page."""

    strip_fragment: bool = _f(
        True, "Treat /page#a and /page as one page.", "URLs", "toggle", advanced=True,
        effect="On: links that differ only after # count as one page. Off: each anchor is crawled as its own page.")
    strip_trailing_slash: bool = _f(
        True, "Treat /page/ and /page as one page.", "URLs", "toggle", advanced=True,
        effect="On: a trailing slash does not make a new page. Off: /page and /page/ are crawled separately.")


def _weights(name: str) -> Any:
    return _f(dict(DEFAULT_WEIGHTS[name]),
              f"Feature weights of the '{name}' priority strategy; depth_penalty is "
              "subtracted per level of depth.", "Priority", "weights", advanced=True,
              effect="Raising one feature's weight ranks links with more of it higher. Raising all of them together makes the NLP part count for more against the LLM score.")


class PriorityConfig(BaseModel):
    """Mix of NLP and LLM scores in a link's priority (priority_pipeline.py)."""

    nlp_bias: float = _f(
        60, "Weight of the NLP score in a link's priority; only its ratio to llm_bias matters.",
        "Priority", "split", unit="", pair="llm_bias", ge=0,
        effect="Raising it lets the cheap similarity score move links up the queue more; only its ratio to the LLM weight matters.")
    llm_bias: float = _f(
        40, "Weight of the LLM score in a link's priority; only its ratio to nlp_bias matters.",
        "Priority", "split", unit="", pair="nlp_bias", ge=0,
        effect="Raising it lets the LLM's judgement move links up the queue more; only its ratio to the NLP weight matters.")

    aggressive_weights: dict[str, float] = _weights("aggressive")
    balanced_weights: dict[str, float] = _weights("balanced")
    exploration_weights: dict[str, float] = _weights("exploration")

    @model_validator(mode="after")
    def _known_weights(self) -> "PriorityConfig":
        for name in DEFAULT_WEIGHTS:
            unknown = set(getattr(self, f"{name}_weights")) - WEIGHT_KEYS
            if unknown:
                raise ValueError(
                    f"The {name} priority strategy weights features the crawler does not have: "
                    f"{', '.join(sorted(unknown))}."
                )
        return self

    @model_validator(mode="after")
    def _positive_sum(self) -> "PriorityConfig":
        if self.nlp_bias + self.llm_bias <= 0:
            raise ValueError("The NLP and LLM shares cannot both be zero.")
        return self


class NlpConfig(BaseModel):
    """NLP composite score (services/nlp_service.py)."""

    composite_weights: dict[str, float] = _f(
        dict(_config.NLP_COMPOSITE_WEIGHTS),
        "Feature weights of the composite NLP score (negative subtracts).",
        "NLP", "weights",
        effect="Raising a feature's weight adds more of it to the NLP score; a negative weight lowers the score.")
    target_top_k: int = _f(
        2, "Nearest target-basis vectors averaged into target similarity.",
        "NLP", "slider", unit="", step=1, ge=1, le=10,
        effect="Averages more reference vectors into each link's topic similarity, so one odd reference counts for less.")
    cluster_eps: float = _f(
        0.3, "DBSCAN cosine radius used to find clusters in the semantic space.",
        "NLP", advanced=True, gt=0.0,
        effect="A larger radius groups looser neighbours into one cluster, so fewer pages count as new.")
    cluster_min_samples: int = _f(
        2, "DBSCAN minimum points per cluster.",
        "NLP", advanced=True, ge=1,
        effect="Higher values need more similar pages before a cluster forms, so fewer clusters are found.")
    link_context_length: int = _f(
        100, "Characters of surrounding text kept as a link's context.",
        "NLP", "slider", unit="chars", step=10, ge=10, le=1000,
        effect="More surrounding text gives each link more to score on, and costs more time and tokens.")


class LlmConfig(BaseModel):
    """Request parameters shared by every LLM provider call."""

    max_calls_per_crawl: int | None = _f(
        None, "Total LLM calls one crawl may make; empty means no cap.",
        "LLM", unit="calls", ge=1,
        effect="At the cap the crawl keeps going, but links the LLM would have judged are scored on NLP alone.")
    max_tokens: int | None = _f(
        None, "Completion token cap; empty uses the provider default.",
        "LLM", unit="tokens", ge=1,
        effect="Caps how long each LLM reply can be; a cap that is too low cuts replies short.")
    temperature: float | None = _f(
        None, "Sampling temperature; empty uses the provider default.",
        "LLM", unit="", ge=0.0, le=2.0,
        effect="Higher values make the LLM's judgements vary more between calls; lower values make them more repeatable.")
    key_cooldown_seconds: float = _f(
        0.0, "Minimum gap before the same API key is reused.",
        "LLM", unit="s", ge=0.0,
        effect="After a key is used it waits this long before it is used again, which spreads requests across keys.")


class ObservabilityConfig(BaseModel):
    debug_enabled: bool = _f(
        _config.DEBUG, "Write the per-crawl debug trace file.",
        "Observability", "toggle",
        effect="On writes a detailed trace file for each crawl, which takes disk space.")
    ui_port: int = _f(
        8765, "Websocket port the live graph connects to.",
        "Observability", unit="", ge=1, le=65535,
        effect="Changing it means the live graph page has to connect to the new port.")
    snapshot_max_candidates: int = _f(
        4000, "Scoring decisions kept for the live view.",
        "Observability", advanced=True, ge=1,
        effect="Caps how many scoring decisions the live view can show; older ones are dropped.")
    snapshot_max_errors: int = _f(
        1000, "Crawl errors kept for the live view.",
        "Observability", advanced=True, ge=1,
        effect="Caps how many crawl errors the live view keeps; older ones are dropped.")


class PromptsConfig(BaseModel):
    """Wording of the scoring prompt (models/prompts.py). The output format
    and JSON constraints are fixed because the response parser depends on
    them."""

    scoring_system: str = _f(
        SCORING_SYSTEM_PROMPT, "System prompt of the link-scoring LLM call.",
        "Prompts", "textarea", min_length=1,
        effect="Changes the instructions the LLM follows on every scoring call; the output format stays fixed so replies still parse.")
    scoring_rules: str = _f(
        SCORING_RULES, "RULES block of the scoring prompt.",
        "Prompts", "textarea", min_length=1,
        effect="Changes the rules the LLM applies when it judges links, on every call.")
    strategy_contexts: dict[str, str] = _f(
        {k: v["context"] for k, v in STRATEGIES.items()},
        "Wording that biases the scoring LLM, per scoring strategy.", "Prompts", "stringmap",
        effect="Each line tilts the LLM toward that strategy's goal, so changing it shifts which links score high.")

    @model_validator(mode="after")
    def _known_strategies(self) -> "PromptsConfig":
        unknown = set(self.strategy_contexts) - set(STRATEGIES)
        if unknown:
            raise ValueError(f"Unknown scoring strategy: {', '.join(sorted(unknown))}.")
        return self


class ProvidersConfig(BaseModel):
    """Request URL per LLM provider (infrastructure/llm_handler.py). Point a
    provider at any compatible server; Gemini takes a base URL."""

    endpoints: dict[str, str] = _f(
        dict(LlmHandler.DEFAULT_ENDPOINTS),
        "Request URL used for each provider.", "Providers", "stringmap",
        effect="Changing a URL sends that provider's requests to another server, such as a local or compatible one.")

    @model_validator(mode="after")
    def _valid(self) -> "ProvidersConfig":
        for name, url in self.endpoints.items():
            if name not in LlmHandler.DEFAULT_ENDPOINTS:
                raise ValueError(f"Unknown LLM provider: {name}.")
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"The {name} endpoint must start with http:// or https://.")
        return self


class RunConfig(BaseModel):
    seed: int | None = _f(
        None, "Seed for every random stream; empty is unseeded.", "Run", unit="",
        effect="A fixed seed makes every random choice repeat, so two runs with the same settings sample the same links.")
    stop_check_interval: float = _f(
        0.1, "Seconds between stop-condition checks on a quiet crawl.",
        "Run", unit="s", advanced=True, gt=0.0,
        effect="Shorter checks stop a quiet crawl sooner but use a little more CPU.")
    shutdown_grace: float = _f(
        5.0, "Seconds the other tasks get to finish once a crawl stops.",
        "Run", unit="s", advanced=True, ge=0.0,
        effect="Longer gives in-flight work more time to finish before the crawl stops; shorter stops sooner.")


SECTION_GUIDE = [
    ("Scoring cascade", "Decides which links the cheap NLP score settles and which are worth an LLM call."),
    ("Fetch", "How fast and how politely pages are requested, and how the crawler backs off."),
    ("Priority", "How the queue of pages still to visit is ordered: the NLP and LLM shares, and the weights of each priority strategy."),
    ("Prompts", "The instructions the LLM receives when it judges a batch of links."),
    ("Providers", "Which LLM service answers, and which models it may use."),
    ("Pipelines", "How many workers each stage runs and how long its queue may grow."),
    ("Retries", "What happens to a page whose fetch or scoring failed. Every retry sends another request or LLM call, so retries add load."),
    ("Embeddings", "The model that turns text into vectors for similarity scoring."),
    ("NLP", "How link text and context are turned into a similarity score."),
    ("LLM", "Request limits for the language model calls."),
    ("URLs", "Which links count as the same page."),
    ("Export", "What a finished crawl writes to disk."),
    ("Observability", "Logging, debugging and the live graph connection."),
    ("Run", "Seeds and shutdown timing of a crawl."),
]

# Plain-language definitions the settings page shows on hover or focus.
# Keys are lower-case terms; the page matches them against labels and prose.
GLOSSARY = {
    "percentile": "A link's place in its own page's scores: 90 % means it scores higher than 90 % of that page's links.",
    "cascade": "The two-stage filter: a cheap NLP score settles most links, and only the uncertain ones go to the LLM.",
    "nlp score": "A fast similarity score computed locally from the link's text and its context, with no LLM call.",
    "llm score": "A relevance judgement from the language model, which costs a request per batch of links.",
    "backoff": "The pause the crawler takes after a site answers with too many requests (429), growing with each one.",
    "429": "The HTTP status 'too many requests': the site asks the crawler to slow down.",
    "jitter": "A random extra pause added to each delay so that requests do not arrive on a fixed rhythm.",
    "embedding": "A list of numbers that stands for a text's meaning, so that similar texts get similar numbers.",
    "cosine": "A measure of how closely two embeddings point the same way; 1 is identical direction, 0 is unrelated.",
    "top-k": "Keeping only the k best matches, here the k closest reference vectors to a link.",
    "dbscan": "A clustering method that groups points lying close together and leaves isolated ones out.",
    "queue": "The line of work waiting for a pipeline stage to pick it up.",
    "flush": "Writing the buffered work out at once, instead of waiting for the next scheduled write.",
    "backpressure": "A full queue or buffer making the stage before it wait, so that memory does not grow without limit.",
    "temperature": "How much randomness the LLM uses when it picks its reply; 0 is the most repeatable.",
    "demotion": "Lowering a page's priority so it is crawled later.",
    "worker": "One of the parallel loops that take items from a stage's queue and process them.",
    "priority": "A page's place in the queue; higher priority is crawled sooner.",
    "robots.txt": "A file where a site states which pages automated crawlers may fetch.",
    "seed": "The number that starts a random sequence; the same seed gives the same random choices.",
    "user-agent": "The name a crawler sends with each request so that a site knows who is asking.",
    "harvest": "The share of the first k fetched pages that are relevant; harvest@k is that share over the first k fetches.",
    "llm_all": "Baseline that asks the LLM about every candidate link, instead of letting the NLP score choose which to ask.",
    "no_llm": "Baseline that replays the cascade's expansion without calling the LLM, so it shows what the NLP side does alone.",
    "cascade replay": "The cascade run again from its saved LLM answers; no live LLM calls are made.",
    "novelty injection": "A priority bonus for pages unlike those already seen. Example: after ten bread recipes, a page about bread ovens ranks higher.",
    "coverage gap": "A priority bonus for a topic region the crawl has barely visited. Example: 40 bread pages and no flour page, so flour pages get the boost.",
    "semantic delta": "How far a page's meaning moves from the page that linked to it. Example: a shop's contact page differs from its bread parent page.",
    "random fraction": "Of the high-confidence links sent to the LLM, the share picked at random rather than by NLP rank. Example: at 0.5, half are a random draw.",
    "best-ranked": "The rest of the LLM-bound high-confidence links, taken in NLP rank order. Example: with a 0.5 random fraction, the other half are the top-ranked links.",
    "key cooldown": "Minimum gap before the same API key is reused. Example: at 2 s, one key sends at most one request every 2 s and a second key takes the next.",
    "backoff decay": "How much each successful fetch shrinks the backoff pause (0.5 halves it). Example: a 4 s pause becomes 2 s after one success.",
    "percentile bucketing": "Splitting a page's links by their place in that page's own scores, instead of by fixed cut-offs, so every page has links in every band.",
    "bucket": "A group of links that the cascade treats the same way: dropped, kept to explore, sent to the LLM, or trusted on the NLP score.",
    "middle band": "The links between the two cut-offs. Every one of them goes to the LLM. Raise the low cut-off or lower the high one to shrink it.",
    "high-confidence bucket": "The links the NLP score rates above the high cut-off. Only a share of them goes to the LLM; the rest is trusted.",
    "nlp bias": "The share of a link's priority that comes from its NLP score. Only its ratio to the LLM bias matters.",
    "llm bias": "The share of a link's priority that comes from the LLM's judgement. Only its ratio to the NLP bias matters.",
    "priority points": "The units of a link's priority score, where higher is crawled sooner. A demotion subtracts points, so the page waits longer in the queue.",
    "in flight": "Requests that have been sent and not yet answered. The number of workers caps it.",
    "politeness": "How gently the crawler treats a site: the pause between requests, how many run at once, and how much a site's refusals slow it.",
    "token": "The unit an LLM reads and bills: about four characters of English text.",
    "tokens": "The units an LLM reads and bills: about four characters of English text each. The cost readouts estimate them from the prompt and link text.",
    "template": "A saved blueprint for one kind of crawl. It fixes the target, the seeds and the scoring focus the crawl starts with.",
    "blueprint": "A saved description of one crawl: its target, seeds, scoring focus and extraction schema.",
    "debug trace": "A log of each decision the crawler made for a page, which can include link text. It is written only while debugging is on.",
    "queue bound": "The most items a stage's queue may hold. When it is full, the stage before it waits.",
    "requeue": "Putting a page back in the queue to be tried again later.",
}


class RuntimeConfig(BaseModel):
    """Top-level runtime configuration: everything a researcher would want
    to see before trusting a crawl's results, beyond the per-run blueprint
    (target topic, seeds, extraction schema) already covered by
    config/blueprint_schema.py."""

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
        "ui_sections": [{"name": n, "help": h} for n, h in SECTION_GUIDE],
        "ui_glossary": GLOSSARY})


def default_runtime_config() -> RuntimeConfig:
    """The config currently in effect, read from config.py's constants."""
    return RuntimeConfig()
