"""Runs one policy on one frozen graph through the real pipelines.

Wired like core.Crawler._build_pipelines at concurrency 1 (so the visit order
is deterministic for a seed), minus the LLM, embeddings, exporter, loggers
and UI. The scoring pipeline's LLM stage is a no-op, so every link is
ranked by the policy's own score.
"""
import asyncio
import logging
import random
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import ClassVar

from config import (
    MAX_LLM_LINKS_PER_NODE,
    NLP_HIGH_PERCENTILE,
    NLP_LOW_PERCENTILE,
    NLP_PERCENTILE_BUCKETING,
    PERCENTILE_MIN_LINKS,
)
from core.event_broker import EventBroker
from events import (
    ContentExtractedEvent,
    ContentFilteredEvent,
    EmptyScoreResultsEvent,
    HighScoreLinksEvent,
    LinksScoredEvent,
    NodeAddedEvent,
    PageFetchedEvent,
    PriorityCalculatedEvent,
    PriorityCalculationFailedEvent,
    RequestFailedEvent,
    ScoreRescheduledEvent,
    ScoringCompletedEvent,
    ScoringFailedEvent,
    StopCrawlEvent,
    StorageOperationFailedEvent,
    TransformationCompletedEvent,
)
from models import Domain, Node, Storage
from pipelines import (
    FilteringPipeline,
    PriorityPipeline,
    ProcessingPipeline,
    RequestsPipeline,
    RetryProcessor,
    ScoringPipeline,
    StoragePipeline,
    TransformationPipeline,
)
from pipelines.base_pipeline import SHUTDOWN
from pipelines.frontier_queue import FrontierQueue

from .graph import BASE_URL, FrozenGraph
from .policies import POLICIES

EXTRACTION = {"mode": "document", "fields": {}}


ARMS = ("cascade", "llm_all", "no_llm")


def _passthrough(node, link, nlp_bias, llm_bias) -> float:
    return link._nlp_score


class _NoLlm:
    async def score_links(self, node, links):
        return links


# The cascade runs with the production retry processor's own backoff
# (RetryProcessor default: 2s, doubling, 3 scoring retries). Rate limits are
# absorbed upstream by PacedLlm, so a retry here means the LLM stage itself
# failed. The idle limit only has to outlast one slow LLM call plus backoff:
# time spent waiting on a rate limit does not count towards it (the run loop
# pauses its idle clock while the LLM wrapper reports ``waiting``).
RETRY_BASE_DELAY = 2.0
IDLE_LIMIT = 120.0


class _BudgetGate:
    """LLM wrapper that never answers a call made once the budget is fetched.

    The last page's links are scored after its fetch, and whether that call
    started before the run was stopped depended on timing: a live run and
    its (much faster) replay disagreed about it, so the replay asked for an
    answer that was never recorded. That call cannot change which pages are
    fetched. In lockstep the fetch count at call time is deterministic, so
    the gate keys on it and the same calls are made live and in replay.
    """

    def __init__(self, llm, budget: int):
        self.inner, self.budget = llm, budget
        self.fetched = lambda: 0  # set by _run: pages fetched so far
        self.skipped = 0

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def send(self, context):
        if self.fetched() >= self.budget:
            self.skipped += 1
            await asyncio.Event().wait()  # cancelled when the run ends
        return await self.inner.send(context)


class _CountedFlush:
    """NLPService stand-in that commits semantic-space growth by count, not time.

    The space only changes inside ``update_space``, which ScoringPipeline
    awaits before it moves to the next node, so the growth lands at the same
    point in the scoring sequence on every execution.
    """

    def __init__(self, nlp, updater, every: int):
        self._nlp, self._updater, self._every = nlp, updater, every
        self._nodes = 0

    def __getattr__(self, name):
        return getattr(self._nlp, name)

    async def update_space(self, scoring_results) -> None:
        await self._nlp.update_space(scoring_results)
        self._nodes += 1
        if self._nodes % self._every == 0:
            await self._updater.force_flush()


class _ParkingScoring(ScoringPipeline):
    """ScoringPipeline that says when its worker is only waiting for a page.

    The worker takes the best node off its queue and waits for that page to
    be fetched. Waiting for a fetch is not work in progress, so the lockstep
    gate must tell it apart from scoring."""

    gate = None  # lockstep: callable, true when nothing else is in flight
    _waiting_for = None  # the node whose fetch the worker waits for

    @property
    def parked(self) -> bool:
        """True while the worker waits for a page that is not fetched yet.

        It turns False when the node becomes ready, not when the worker
        resumes. In between, the crawler looked quiet, so the next page was
        taken from the frontier before this page's links were scored.
        """
        node = self._waiting_for
        return node is not None and not node.ready.done()

    async def _worker_loop(self, worker_id: int) -> None:
        # The base loop, except that the worker picks its next node only once
        # the previous node's consequences have landed. Otherwise it would pick
        # before the children of the node it just scored reach the queue, and
        # which node it picked would depend on timing.
        while True:
            polls = 0
            while self.gate is not None and not self.gate():
                polls += 1
                await asyncio.sleep(0 if polls < 200 else 0.0005 if polls < 1000 else 0.005)
            item = await self.queue.get()
            try:
                if item is SHUTDOWN:
                    break
                await self._process(item, worker_id)
            except Exception:
                logging.getLogger("pipelines.base_pipeline").exception(
                    "scoring worker %d failed processing %s", worker_id, type(item).__name__
                )
            finally:
                self.queue.task_done()

    async def _await_ready(self, node):
        if node.ready.done():
            return await super()._await_ready(node)
        self._waiting_for = node
        try:
            return await super()._await_ready(node)
        finally:
            self._waiting_for = None


class _Lockstep:
    """Fetcher wrapper: a page is served only once the crawler is quiet.

    Quiet means every consequence of the previous page has landed: its
    scoring (live LLM calls included), priority calculation, retries and the
    new frontier nodes. Waiting on the clock never decides anything; only
    state does, so the visit order depends on the answers and not on how fast
    they arrived. Live and replayed runs therefore walk the same pages.
    """

    def __init__(self, fetcher, quiet, budget: int | None = None):
        self.fetcher, self.quiet, self.budget = fetcher, quiet, budget

    @property
    def fetched(self):
        return self.fetcher.fetched

    async def emit_request(self, params: dict) -> str:
        polls = 0
        while not self.quiet():
            # Spin while work is moving through the event loop, back off while
            # waiting on a slow LLM call. The wait only costs time.
            polls += 1
            await asyncio.sleep(0 if polls < 200 else 0.0005 if polls < 1000 else 0.005)
        if self.budget is not None and len(self.fetcher.fetched) >= self.budget:
            # The budget is spent. Without this, nodes the cheap tiers score
            # without an LLM call kept the crawler quiet and it fetched on
            # until one needed the LLM (hundreds of pages past the budget).
            await asyncio.Event().wait()  # cancelled when the run ends
        return await self.fetcher.emit_request(params)

    async def close(self) -> None:
        await self.fetcher.close()


class _QuietQueue(FrontierQueue):
    """Frontier whose ``get`` pops only once the crawler is quiet.

    A worker blocked in ``get`` takes whichever node arrives first, so the
    page it fetches depended on the order children reached the queue, which
    varies with event-loop scheduling (a live LLM call and a cached answer
    interleave differently). Waiting for quiet and then popping lets the
    queue choose among all of the previous page's children by priority.
    """

    gate = None  # callable: true when nothing else is in flight

    async def get(self):
        polls = 0
        while self.gate is not None and not (self.gate() and not self.empty()):
            polls += 1
            await asyncio.sleep(0 if polls < 200 else 0.0005 if polls < 1000 else 0.005)
        return self.get_nowait()


class _NoJitter:
    """Politeness jitter is for live sites; a frozen graph needs none."""

    def uniform(self, a, b) -> float:
        return 0.0


class _ErrorLog(logging.Handler):
    """Collects exceptions the pipelines log and swallow (worker safety nets)."""

    def __init__(self):
        super().__init__(logging.ERROR)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.exc_info:
            self.records.append(f"{record.name}: {record.getMessage()}")


class HealthMonitor:
    """Counts what went wrong during a run. Subscribed like a pipeline.

    Two kinds of finding, kept apart on purpose:
      * run failures (``problems``): the benchmark did not execute the
        experiment it claims to have. The repeat is invalid and must not
        enter any statistic.
      * system behavior (``scoring_failures``, ``empty_results``): the LLM
        stage failed or answered nothing for a node, and the cascade handled
        it (the node was rescheduled and later scored). Part of the
        measurement; reported next to it.
    """

    EVENTS: ClassVar[list[type]] = [
        ScoringFailedEvent,
        EmptyScoreResultsEvent,
        ScoringCompletedEvent,
        PriorityCalculationFailedEvent,
        StorageOperationFailedEvent,
        RequestFailedEvent,
    ]

    def __init__(self):
        self.handlers = {t: self._count for t in self.EVENTS}
        self.counts: dict[str, int] = {}
        self.scoring_failed: dict[str, str] = {}  # node -> error type, until it scores
        self.empty: set[str] = set()
        self.scored: set[str] = set()
        self.failures_seen = 0
        self.empties_seen = 0

    async def put(self, event) -> None:
        await self.handlers[type(event)](event)

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def _count(self, event) -> None:
        name = type(event).__name__
        self.counts[name] = self.counts.get(name, 0) + 1
        node = getattr(event, "correlation_id", "?")
        if isinstance(event, ScoringFailedEvent):
            self.failures_seen += 1
            self.scoring_failed[node] = event.error_type
        elif isinstance(event, EmptyScoreResultsEvent):
            self.empties_seen += 1
            self.empty.add(node)
        elif isinstance(event, ScoringCompletedEvent):
            # An empty answer also completes (with no links) before its retry.
            if event.scored_links or node not in self.empty:
                self.scored.add(node)
                self.scoring_failed.pop(node, None)


@dataclass
class RunHealth:
    nodes_fetched: int = 0
    nodes_scored: int = 0
    scoring_failures: int = 0  # LLM stage raised; handled by retry (behavior)
    empty_results: int = 0  # LLM stage answered nothing; handled by retry (behavior)
    retries_exhausted: int = 0  # a node gave up scoring (run failure)
    status: str = "completed"  # completed | completed_early | failed
    reason: str = ""  # for completed_early: frontier_exhausted
    problems: list[str] = field(default_factory=list)  # run failures

    @property
    def valid(self) -> bool:
        return not self.problems


def assess(budget, fetched, monitor, retry, errors, frontier_empty: bool = False) -> RunHealth:
    h = RunHealth(
        nodes_fetched=len(fetched),
        nodes_scored=len(monitor.scored),
        scoring_failures=monitor.failures_seen,
        empty_results=monitor.empties_seen,
    )
    exhausted = [n for n, c in retry._scoring_retry_counts.items() if c > retry.max_scoring_retries]
    h.retries_exhausted = len(exhausted)
    if len(fetched) < budget:
        if frontier_empty and not exhausted:
            # The policy ran out of pages it would admit. That is behaviour to
            # measure, not a failed run.
            h.status, h.reason = "completed_early", "frontier_exhausted"
        else:
            h.problems.append(f"stalled with work pending after {len(fetched)} of {budget} pages")
    if exhausted:
        h.problems.append(f"{len(exhausted)} node(s) gave up scoring after {retry.max_scoring_retries} retries")
    for name in ("PriorityCalculationFailedEvent", "StorageOperationFailedEvent", "RequestFailedEvent"):
        if monitor.counts.get(name):
            h.problems.append(f"{monitor.counts[name]} {name}")
    if errors.records:
        h.problems.append(f"{len(errors.records)} swallowed pipeline exception(s): {errors.records[0][:120]}")
    if h.problems:
        h.status = "failed"
    return h


@dataclass
class RunResult:
    policy: str
    visited: list[str]  # page names in fetch order
    labels: list[int]  # graded label (0/1/2) of each visited page
    health: RunHealth = field(default_factory=RunHealth)
    wall_seconds: float = 0.0
    rate_limit_seconds: float = 0.0  # wall time spent waiting on pacing or a 429; not idle time
    thresholds: dict = field(default_factory=dict)  # bucketing in force: mode, absolute and percentile values
    absent_page_hits: int = 0  # requests for pages outside the frozen graph (graph.ABSENT_PAGE_HITS)

    def harvest(self, k: int) -> float:
        """Share of the first k fetched pages that are relevant (label >= 1)."""
        labels = self.labels[:k]
        return self.found(k) / len(labels) if labels else 0.0

    def found(self, k: int) -> int:
        """Relevant pages (label >= 1) among the first k fetched."""
        return sum(1 for v in self.labels[:k] if v >= 1)

    def found_direct(self, k: int) -> int:
        """Direct targets (label 2) among the first k fetched."""
        return sum(1 for v in self.labels[:k] if v == 2)


def _thresholds(kwargs: dict, percentiles) -> dict:
    """The bucketing a run used, absolute and percentile values both."""
    if kwargs.get("percentile_bucketing"):
        mode = "percentile"
    elif kwargs["low_threshold"] <= -1.0 and kwargs["high_threshold"] >= 2.0:
        mode = "none"  # every link is admitted (baselines, llm_all)
    else:
        mode = "absolute"
    return {
        "mode": mode,
        "low": kwargs["low_threshold"], "high": kwargs["high_threshold"],
        "low_percentile": percentiles[0], "high_percentile": percentiles[1],
    }


async def run_policy(
    graph: FrozenGraph, policy: str, budget: int, seed: int = 0, lockstep: bool = True,
    extra_components: Sequence[object] = (),
) -> RunResult:
    """Fetch up to `budget` pages (the seed counts) starting from graph.seed.

    ``extra_components`` are subscribed like pipelines, after the run's own
    (see ``_run``); observers such as the behaviour pins use it.
    """
    scoring_args = (
        _NoLlm(), POLICIES[policy](graph, seed),
        # Admit every link: a ranking baseline must not inherit the cascade's
        # bucketing, which drops low-NLP links before they reach the frontier.
    )
    scoring_kwargs = {
        "low_threshold": -1.0,
        "high_threshold": 2.0,
        "high_score_llm_fraction": 0.0,
        "low_score_sample_fraction": 0.0,
        "high_score_random_fraction": 0.0,
        "percentile_bucketing": False,
        "max_llm_links": None,
    }
    return await _run(
        graph, policy, budget, seed, scoring_args, scoring_kwargs, _passthrough,
        list(extra_components), lockstep=lockstep,
    )


async def _run(
    graph, label, budget, seed, scoring_args, scoring_kwargs, strategy, extra,
    extraction=EXTRACTION, retry_base_delay=0.01, idle_limit=0.5, lockstep=True,
    rate_limited=None, budget_gate=None, percentiles=(NLP_LOW_PERCENTILE, NLP_HIGH_PERCENTILE),
) -> RunResult:
    """One lockstep run. Each component in ``extra`` has ``handlers`` (event
    type to coroutine), ``start`` and ``put``, and is subscribed to the events
    its ``handlers`` name, after the run's own pipelines. An extra component
    is an observer: it does not change the pages the run visits."""
    fetcher = graph.fetcher()
    if budget_gate is not None:
        budget_gate.fetched = lambda: len(fetcher.fetched)
    broker, storage = EventBroker(), Storage()
    domain = Domain("frozen", BASE_URL, ".//a")
    storage.add_domain(domain)

    gated = _Lockstep(fetcher, lambda: False, budget) if lockstep else fetcher
    requests = RequestsPipeline(
        broker, max_concurrency=1, fetcher=gated, min_delay=0,
        rng=_NoJitter(),
    )
    if lockstep:
        requests.queue = _QuietQueue()
    scoring = _ParkingScoring(
        *scoring_args,
        broker,
        low_percentile=percentiles[0],
        high_percentile=percentiles[1],
        percentile_min_links=PERCENTILE_MIN_LINKS,
        rng=random.Random(f"{seed}:scoring"),
        **scoring_kwargs,
    )
    retry = RetryProcessor(storage, broker, requests_pipeline=requests, retry_base_delay=retry_base_delay)
    processing = ProcessingPipeline(broker, extraction)
    filtering = FilteringPipeline(broker, storage)
    transformation = TransformationPipeline(broker, extraction)
    store = StoragePipeline(storage, broker)
    priority = PriorityPipeline(storage, broker)
    if strategy is not None:
        priority.strategy = strategy  # not registered: the registry is global
    pipelines = [requests, processing, filtering, transformation, store, scoring, priority, retry]
    monitor = HealthMonitor()
    pipelines += extra

    broker.subscribe(requests, [NodeAddedEvent])
    broker.subscribe(processing, [PageFetchedEvent])
    broker.subscribe(filtering, [ContentExtractedEvent])
    broker.subscribe(transformation, [ContentFilteredEvent])
    broker.subscribe(
        store, [PriorityCalculatedEvent, TransformationCompletedEvent, PageFetchedEvent]
    )
    broker.subscribe(scoring, [NodeAddedEvent, ScoreRescheduledEvent])
    broker.subscribe(priority, [LinksScoredEvent, HighScoreLinksEvent])
    for component in extra:
        broker.subscribe(component, list(component.handlers))
    broker.subscribe(monitor, HealthMonitor.EVENTS)
    broker.subscribe(retry, [EmptyScoreResultsEvent, RequestFailedEvent, ScoringFailedEvent])

    if lockstep:
        idle_pipelines = [processing, filtering, transformation, store, priority, retry]

        def others_idle() -> bool:
            return (
                broker.event_bus.empty()
                and not broker.active_tasks
                and all(p.queue._unfinished_tasks == 0 for p in idle_pipelines)
                and not retry._pending
            )

        gated.quiet = lambda: others_idle() and (scoring.queue._unfinished_tasks == 0 or scoring.parked)
        scoring.gate = others_idle
        requests.queue.gate = gated.quiet
    errors = _ErrorLog()
    logging.getLogger().addHandler(errors)
    started = time.monotonic()
    tasks = [asyncio.create_task(broker.start())] + [asyncio.create_task(p.start()) for p in pipelines]
    await asyncio.sleep(0.05)
    seed_node = Node(storage.next_id(), url=f"{BASE_URL}/{graph.seed}", domain=domain, priority=0.01)
    storage.add_node(seed_node)
    await broker.emit(NodeAddedEvent(correlation_id=str(seed_node.get_id()), node=seed_node))

    # Done when the budget is met, or nothing new has been fetched for a while.
    def frontier_empty() -> bool:
        return (
            requests.queue.empty()
            and scoring.queue._unfinished_tasks == 0
            and not retry._pending
        )

    last, idle, empty_for, rate_limit_wait = 0, 0.0, 0.0, 0.0
    while len(fetcher.fetched) < budget and idle < idle_limit and empty_for < 0.5:
        await asyncio.sleep(0.02)
        if rate_limited is not None and rate_limited():
            # Waiting out a rate limit is neither progress nor a stall: the
            # idle clock stops and the time is counted on its own.
            rate_limit_wait += 0.02
        else:
            idle = idle + 0.02 if len(fetcher.fetched) == last else 0.0
        last = len(fetcher.fetched)
        # In lockstep an empty, quiet frontier is final (the next fetch would
        # have to come from it). Stable for half a second to ride out the hop
        # between a node leaving the queue and its fetch starting.
        empty_for = empty_for + 0.02 if lockstep and gated.quiet() and frontier_empty() else 0.0

    await broker.emit(StopCrawlEvent("NO_PROGRESS", len(storage.nodes), 0, 0.0))
    _, pending = await asyncio.wait(tasks, timeout=2.0)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)

    logging.getLogger().removeHandler(errors)
    wall = time.monotonic() - started
    visited = fetcher.fetched[:budget]
    return RunResult(
        label, visited, [graph.label(p) for p in visited],
        assess(budget, fetcher.fetched, monitor, retry, errors, frontier_empty()),
        wall_seconds=wall, rate_limit_seconds=rate_limit_wait,
        absent_page_hits=fetcher.absent_hits,
        thresholds=_thresholds(scoring_kwargs, percentiles),
    )


async def run_cascade(
    graph: FrozenGraph,
    budget: int,
    seed: int,
    llm,
    extraction: dict,
    expansion: dict,
    scoring_strategy: str,
    model: tuple[str, str],
    store_dir,
    flush_every: int = 8,
    lockstep: bool = True,
    arm: str = "cascade",
    low: float | None = None,
    high: float | None = None,
    low_pct: float | None = None,
    high_pct: float | None = None,
    extra_components: Sequence[object] = (),
) -> RunResult:
    """The real cascade (embedding model, topic expansion, LLM scoring,
    bucketing, priority strategy) on a frozen graph. `llm` is anything with
    ``send(context)``; wrap the real handler in ``CachedLlm`` so a rerun is
    free and repeatable. Cascade settings come from the default runtime
    config, as a normal crawl would use them.

    ``arm`` picks the experiment:

    * ``cascade``: the production cascade.
    * ``llm_all``: every discovered link goes to the LLM, with the cascade's
      prompt and batch size (``MAX_LLM_LINKS_PER_NODE`` links per call) and no
      embedding-based bucketing. NLP scores are still computed, because the
      priority strategy blends them, but they decide nothing about who is sent.
    * ``no_llm``: embedding scores only. No scoring call is made and no
      expansion is learned from answers. The topic basis comes from ``llm``
      (the caller replays the cascade's recorded expansion), so it is the
      same as the cascade's.

    ``low_pct`` / ``high_pct`` replace the percentiles (20 / 75) of the
    default percentile bucketing, which stays on.

    ``low`` / ``high`` replace the absolute bucketing thresholds. The
    percentile bucketing the cascade normally uses would make them inert for
    nodes with enough links, so giving either switches it off.

    ``extra_components`` are subscribed like pipelines, after the run's own
    (see ``_run``); observers such as the behaviour pins use it.
    """
    from config.runtime_config import default_runtime_config
    from nlp import BufferManager, SpaceUpdater
    from priority.strategy import get_strategy
    from services import NLPService, ScoringService

    cfg = default_runtime_config()
    llm = gate = _BudgetGate(llm, budget)
    buffer_manager = BufferManager(max_size=cfg.embeddings.buffer_max_size)
    nlp = NLPService(
        blueprint_id="benchmark",
        target_topic=graph.topic,
        llm_handler=llm,
        expansion_config=expansion,
        embedding_backend=cfg.embeddings.backend,
        model_name=cfg.embeddings.model_name,
        store_base_dir=str(store_dir),
        persist_space=False,
        buffer_manager=buffer_manager,
    )
    await nlp.start()
    updater = SpaceUpdater(
        nlp_service=nlp,
        buffer_manager=buffer_manager,
        flush_interval=cfg.embeddings.flush_interval_seconds,
        flush_threshold=cfg.embeddings.flush_threshold,
    )
    # SpaceUpdater is never started: its wall-clock timer would change the
    # semantic space at a moment that depends on machine speed. Growth is
    # committed after every `flush_every` scored nodes instead.
    nlp = _CountedFlush(nlp, updater, flush_every)
    llm_service = ScoringService(llm, graph.topic, scoring_strategy, *model)
    c = cfg.scoring_cascade
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}; expected one of {ARMS}")
    pct_given = low_pct is not None or high_pct is not None
    if arm != "cascade" and (low is not None or high is not None or pct_given):
        raise ValueError("low/high and low_pct/high_pct only apply to the cascade arm")
    if pct_given and (low is not None or high is not None):
        raise ValueError("absolute thresholds and percentiles are different bucketing modes; give one")
    percentiles = (
        NLP_LOW_PERCENTILE if low_pct is None else low_pct,
        NLP_HIGH_PERCENTILE if high_pct is None else high_pct,
    )
    if not 0 <= percentiles[0] < percentiles[1] <= 100:
        raise ValueError(f"low_pct ({percentiles[0]}) must be below high_pct ({percentiles[1]}), within 0..100")
    kwargs = {
        "low_threshold": c.low_threshold if low is None else low,
        "high_threshold": c.high_threshold if high is None else high,
        "high_score_llm_fraction": c.high_score_llm_fraction,
        "low_score_sample_fraction": c.low_score_sample_fraction,
        "high_score_random_fraction": c.high_score_random_fraction,
        "percentile_bucketing": NLP_PERCENTILE_BUCKETING and low is None and high is None,
        "max_llm_links": MAX_LLM_LINKS_PER_NODE,
    }
    if kwargs["low_threshold"] >= kwargs["high_threshold"]:
        raise ValueError(f"low ({kwargs['low_threshold']}) must be below high ({kwargs['high_threshold']})")
    if arm == "llm_all":
        kwargs.update(
            low_threshold=-1.0, high_threshold=2.0, percentile_bucketing=False,
            high_score_llm_fraction=0.0, low_score_sample_fraction=0.0,
            high_score_random_fraction=0.0, max_llm_links=None,
            llm_batch_size=MAX_LLM_LINKS_PER_NODE,
        )
    elif arm == "no_llm":
        kwargs.update(
            high_score_llm_fraction=0.0, low_score_sample_fraction=0.0,
            high_score_random_fraction=0.0, max_llm_links=None,
        )
        llm_service = _NoLlm()
    return await _run(
        graph, arm, budget, seed, (llm_service, nlp), kwargs,
        get_strategy(c.default_priority_strategy), list(extra_components), extraction,
        retry_base_delay=RETRY_BASE_DELAY, idle_limit=IDLE_LIMIT, lockstep=lockstep,
        rate_limited=lambda: bool(getattr(llm, "waiting", False)),
        budget_gate=gate, percentiles=percentiles,
    )
