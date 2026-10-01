"""Runtime invariants for the crawl pipelines, checked end to end.

Each test wires the real pipelines by hand (the way core/crawler.py's
_build_pipelines / _wire_subscriptions do) around a fake fetcher serving a
small synthetic site and a heuristic stand-in for NLPService/ScoringService.
No API keys, embedding model, network, items.db, logs/ or export/ are
involved, so these run anywhere in a few seconds.

Every test here currently fails against the code it describes and is marked
``xfail(strict=True)``: the marker documents a known defect, and the strict
flag turns the fix into a visible XPASS that forces the marker's removal.
"""
import asyncio
import logging
import types

import pytest

from config import (
    HIGH_SCORE_LLM_FRACTION,
    HIGH_SCORE_RANDOM_FRACTION,
    LOW_SCORE_SAMPLE_FRACTION,
    MAX_LLM_LINKS_PER_NODE,
    NLP_HIGH_PERCENTILE,
    NLP_HIGH_SCORE_THRESHOLD,
    NLP_LOW_PERCENTILE,
    NLP_LOW_SCORE_THRESHOLD,
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
    NoLinksToScoreEvent,
    PageFetchedEvent,
    PriorityCalculatedEvent,
    RequestFailedEvent,
    ScoreRescheduledEvent,
    ScoringFailedEvent,
    StopCrawlEvent,
    TransformationCompletedEvent,
)
from models import Domain, Link, Node, Storage
from pipelines import (
    FilteringPipeline,
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

BASE_URL = "https://synthetic.test"
EXTRACTION = {"mode": "document", "fields": {}}


# =========================================================
# FAKES
# =========================================================

class SyntheticSite:
    """Fake fetcher: serves `graph` (page -> outgoing pages) as HTML.

    Pages listed in `dead` always fail, like a permanent 404.
    """

    def __init__(self, graph: dict[str, list[str]], dead: frozenset[str] = frozenset()):
        self.graph = graph
        self.dead = dead
        self.fetched: list[str] = []

    async def emit_request(self, params: dict) -> str:
        page = params["url"].rsplit("/", 1)[1]
        if page in self.dead:
            raise RuntimeError("404 Not Found")
        self.fetched.append(page)
        anchors = "".join(f'<li><a href="/{t}">{t}</a></li>' for t in self.graph.get(page, []))
        return f"<html><body><h1>{page}</h1><ul>{anchors}</ul></body></html>"

    async def close(self) -> None:
        pass


class FixedRelevance:
    """Stands in for NLPService: every link gets the same NLP score."""

    def __init__(self, score: float):
        self.score = score
        self.calls = 0

    async def score_links(self, links, parent):
        self.calls += 1
        for link in links:
            link._nlp_score = self.score
            link.nlp_vector = {"target_similarity": self.score}
        return links

    async def update_space(self, links) -> None:
        pass


class FixedLlm:
    """Stands in for ScoringService: every sampled link gets the same LLM score."""

    async def score_links(self, node, links):
        for link in links:
            link.score = 50
        return links


class Recorder:
    """Broker subscriber that keeps every event it receives."""

    def __init__(self):
        self.events: list = []

    async def put(self, event) -> None:
        self.events.append(event)

    def of(self, event_type) -> list:
        return [e for e in self.events if isinstance(e, event_type)]


# =========================================================
# HARNESS
# =========================================================

def make_scoring(broker, nlp, llm) -> ScoringPipeline:
    """ScoringPipeline built with the same arguments core.Crawler passes."""
    return ScoringPipeline(
        llm,
        nlp,
        broker,
        low_threshold=NLP_LOW_SCORE_THRESHOLD,
        high_threshold=NLP_HIGH_SCORE_THRESHOLD,
        high_score_llm_fraction=HIGH_SCORE_LLM_FRACTION,
        low_score_sample_fraction=LOW_SCORE_SAMPLE_FRACTION,
        high_score_random_fraction=HIGH_SCORE_RANDOM_FRACTION,
        percentile_bucketing=NLP_PERCENTILE_BUCKETING,
        low_percentile=NLP_LOW_PERCENTILE,
        high_percentile=NLP_HIGH_PERCENTILE,
        percentile_min_links=PERCENTILE_MIN_LINKS,
        max_llm_links=MAX_LLM_LINKS_PER_NODE,
    )


def seed_node(storage: Storage, domain: Domain, page: str, priority: float = 0.01) -> Node:
    node = Node(storage.next_id(), url=f"{BASE_URL}/{page}", domain=domain, priority=priority)
    storage.add_node(node)
    return node


async def stop_all(tasks: list[asyncio.Task], timeout: float = 2.0) -> set[asyncio.Task]:
    """Wait up to `timeout` for `tasks`, cancel any still running, and
    return the ones that had to be cancelled (empty set = clean shutdown).
    """
    _, pending = await asyncio.wait(tasks, timeout=timeout)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    return pending


async def wait_until(predicate, timeout: float) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.02)
    return predicate()


class Crawl:
    """The traversal pipelines of one crawl, wired like core.Crawler but
    without the LLM/embedding services, exporter, loggers or UI layer.
    """

    def __init__(self, site: SyntheticSite, nlp, llm):
        self.broker = EventBroker()
        self.storage = Storage()
        self.domain = Domain("synthetic", BASE_URL, ".//a")
        self.storage.add_domain(self.domain)
        self.site = site
        self.recorder = Recorder()

        b, s = self.broker, self.storage
        self.requests = RequestsPipeline(b, max_concurrency=1, fetcher=site, min_delay=0)
        self.scoring = make_scoring(b, nlp, llm)
        self.retry = RetryProcessor(s, b, requests_pipeline=self.requests, retry_base_delay=0.01)
        self.pipelines = [
            self.requests,
            ProcessingPipeline(b, EXTRACTION),
            FilteringPipeline(b, s),
            TransformationPipeline(b, EXTRACTION),
            StoragePipeline(s, b),
            self.scoring,
            PriorityPipeline(s, b),
            self.retry,
        ]
        requests, processing, filtering, transformation, storage, scoring, priority, retry = (
            self.pipelines
        )
        b.subscribe(requests, [NodeAddedEvent])
        b.subscribe(processing, [PageFetchedEvent])
        b.subscribe(filtering, [ContentExtractedEvent])
        b.subscribe(transformation, [ContentFilteredEvent])
        b.subscribe(
            storage, [PriorityCalculatedEvent, TransformationCompletedEvent, PageFetchedEvent]
        )
        b.subscribe(scoring, [NodeAddedEvent, ScoreRescheduledEvent])
        b.subscribe(priority, [LinksScoredEvent, HighScoreLinksEvent])
        b.subscribe(retry, [EmptyScoreResultsEvent, RequestFailedEvent, ScoringFailedEvent])
        b.subscribe(
            self.recorder,
            [PageFetchedEvent, LinksScoredEvent, NoLinksToScoreEvent, EmptyScoreResultsEvent],
        )
        self.tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        self.tasks = [asyncio.create_task(self.broker.start())] + [
            asyncio.create_task(p.start()) for p in self.pipelines
        ]
        await asyncio.sleep(0.05)  # let every worker block on its queue

    async def add_seed(self, page: str) -> Node:
        node = seed_node(self.storage, self.domain, page)
        await self.broker.emit(NodeAddedEvent(correlation_id=str(node.get_id()), node=node))
        return node

    def scored_ids(self) -> set[int]:
        done = (LinksScoredEvent, NoLinksToScoreEvent, EmptyScoreResultsEvent)
        return {e.node.get_id() for e in self.recorder.events if isinstance(e, done)}

    async def stop(self) -> set[asyncio.Task]:
        await self.broker.emit(StopCrawlEvent("NO_PROGRESS", len(self.storage.nodes), 0, 0.0))
        return await stop_all(self.tasks)


# =========================================================
# 1. FRONTIER ORDER
# =========================================================

async def test_higher_priority_node_is_fetched_first():
    site = SyntheticSite({})
    requests = RequestsPipeline(EventBroker(), max_concurrency=1, fetcher=site, min_delay=0)
    domain = Domain("synthetic", BASE_URL, ".//a")

    for node_id, (page, priority) in enumerate([("mid", 20.0), ("best", 40.0), ("worst", 0.5)]):
        node = Node(node_id, url=f"{BASE_URL}/{page}", domain=domain, priority=priority)
        await requests.queue.put(node)

    task = asyncio.create_task(requests.start())
    try:
        assert await wait_until(lambda: len(site.fetched) == 3, timeout=2.0)
    finally:
        await requests.stop()
        await stop_all([task])

    assert site.fetched == ["best", "mid", "worst"]


# =========================================================
# 2. A DEAD LINK MUST NOT FREEZE SCORING
# =========================================================

async def test_dead_link_does_not_stop_other_nodes_being_scored():
    site = SyntheticSite({"good": ["x", "y"]}, dead=frozenset({"dead"}))
    crawl = Crawl(site, FixedRelevance(0.5), FixedLlm())
    await crawl.start()

    await crawl.add_seed("dead")  # claimed first by the scoring worker
    good = await crawl.add_seed("good")

    try:
        await wait_until(lambda: "good" in site.fetched, timeout=2.0)
        scored = await wait_until(lambda: good.get_id() in crawl.scored_ids(), timeout=2.0)
    finally:
        await crawl.stop()

    assert "good" in site.fetched
    assert scored, "a successfully fetched node was never scored"


# =========================================================
# 3. AN EMPTY LLM SAMPLE IS NOT A FAILURE
# =========================================================

async def _score_one_ready_node(nlp_score: float, run_for: float):
    """Score one already-fetched node whose 3 links all get `nlp_score`.

    With fewer than PERCENTILE_MIN_LINKS links the absolute thresholds
    apply, so every link lands in the same bucket and the LLM sample is
    empty by design.
    """
    broker, storage = EventBroker(), Storage()
    domain = Domain("synthetic", BASE_URL, ".//a")
    nlp = FixedRelevance(nlp_score)
    scoring = make_scoring(broker, nlp, FixedLlm())
    pipelines = [
        scoring,
        RetryProcessor(storage, broker),
        PriorityPipeline(storage, broker),
        StoragePipeline(storage, broker),
    ]
    recorder = Recorder()
    broker.subscribe(scoring, [NodeAddedEvent, ScoreRescheduledEvent])
    broker.subscribe(pipelines[1], [EmptyScoreResultsEvent, ScoringFailedEvent])
    broker.subscribe(pipelines[2], [LinksScoredEvent, HighScoreLinksEvent])
    broker.subscribe(pipelines[3], [PriorityCalculatedEvent])
    broker.subscribe(recorder, [NodeAddedEvent, ScoreRescheduledEvent])

    node = seed_node(storage, domain, "page")
    node.set_links([Link(f"{BASE_URL}/c{i}", f"c{i}", "") for i in range(3)])
    node.update_state()  # fetched, extracted, filtered, transformed

    tasks = [asyncio.create_task(broker.start())] + [
        asyncio.create_task(p.start()) for p in pipelines
    ]
    await broker.emit(NodeAddedEvent(correlation_id=str(node.get_id()), node=node))
    await asyncio.sleep(run_for)
    await broker.emit(StopCrawlEvent("NO_PROGRESS", 1, 0, run_for))
    await stop_all(tasks)

    children = [e.node.link.url for e in recorder.of(NodeAddedEvent) if e.node is not node]
    return nlp.calls, len(recorder.of(ScoreRescheduledEvent)), children


async def test_node_with_all_low_links_is_not_rescored_indefinitely():
    nlp_calls, reschedules, _ = await _score_one_ready_node(nlp_score=0.10, run_for=0.5)

    assert reschedules <= 3
    assert nlp_calls <= 4


async def test_rescoring_does_not_create_duplicate_children():
    _, _, children = await _score_one_ready_node(nlp_score=0.90, run_for=0.5)

    assert children
    assert len(children) == len(set(children))


async def test_empty_llm_sample_raises_no_errors(caplog):
    with caplog.at_level(logging.ERROR, logger="core.event_broker"):
        await _score_one_ready_node(nlp_score=0.10, run_for=0.2)

    failures = [r.getMessage() for r in caplog.records if r.name == "core.event_broker"]
    assert failures == []


# =========================================================
# 4. A STOPPED CRAWL ACTUALLY ENDS
# =========================================================

@pytest.mark.xfail(
    strict=True,
    reason="A scoring worker awaiting node.ready never reads the SHUTDOWN "
    "sentinel, and after StopCrawlEvent the events that would resolve it are "
    "dropped by the broker.",
)
async def test_scoring_finishes_after_stop_with_a_node_in_flight():
    broker, storage = EventBroker(), Storage()
    scoring = make_scoring(broker, FixedRelevance(0.5), FixedLlm())
    broker.subscribe(scoring, [NodeAddedEvent])
    tasks = [asyncio.create_task(broker.start()), asyncio.create_task(scoring.start())]

    # Claimed by the scoring worker, but its page is still being processed
    # when the crawl stops, so node.ready is never resolved.
    node = seed_node(storage, Domain("synthetic", BASE_URL, ".//a"), "in_flight")
    await broker.emit(NodeAddedEvent(correlation_id=str(node.get_id()), node=node))
    await asyncio.sleep(0.1)
    await broker.emit(StopCrawlEvent("MAX_NODES_REACHED", 1, 0, 0.1))

    still_running = await stop_all(tasks)

    assert not still_running, f"{len(still_running)} task(s) still running after stop"


async def test_gateway_stops_when_the_crawl_stops():
    from ui_bridge import CrawlStateSnapshot, TelemetryBridge, UIWebSocketGateway

    broker = EventBroker()
    snapshot = CrawlStateSnapshot()
    gateway = UIWebSocketGateway(snapshot, port=0)
    telemetry = TelemetryBridge(snapshot, gateway)
    telemetry.register_handlers()
    broker.subscribe(telemetry, [StopCrawlEvent])

    gateway_task = asyncio.create_task(gateway.start())
    broker_task = asyncio.create_task(broker.start())
    await asyncio.sleep(0.1)
    await broker.emit(StopCrawlEvent("MAX_NODES_REACHED", 1, 0, 0.0))

    try:
        await asyncio.wait_for(asyncio.shield(broker_task), timeout=2.0)
        gateway_done = await wait_until(gateway_task.done, timeout=2.0)
    finally:
        await gateway.stop()
        await stop_all([gateway_task, broker_task])

    assert gateway_done


async def test_time_limit_fires_without_further_events():
    broker = EventBroker()
    stopping = StoppingPipeline(
        broker, StopConditions(max_nodes=100, max_duration=0.2, no_progress_timeout=60)
    )
    task = asyncio.create_task(stopping.start())

    try:
        fired = await wait_until(lambda: stopping.stopped, timeout=1.0)
    finally:
        await stopping.stop()
        await stop_all([task])

    assert fired


async def test_link_back_to_the_seed_creates_no_child():
    class _Broker:
        async def emit(self, event):
            pass

    storage = Storage()
    domain = Domain("synthetic", BASE_URL, ".//a")
    seed = seed_node(storage, domain, "page")
    pipeline = StoragePipeline(storage, _Broker())

    await pipeline._on_priority_calculated(
        types.SimpleNamespace(
            parent=seed,
            links=[{"link": Link(f"{BASE_URL}/page", "page", ""), "score": 0, "priority": 0.5}],
        )
    )

    assert len(storage.nodes) == 1


# =========================================================
# 5. BUDGET SEMANTICS (docs/06-algorithms.md §7)
# =========================================================

CHAIN = {"a": ["b"], "b": ["c"], "c": ["d"], "d": ["e"], "e": []}


async def _run_stopping_crawl(max_nodes: int, max_depth: int):
    crawl = Crawl(SyntheticSite(CHAIN), FixedRelevance(0.5), FixedLlm())
    storage_pipeline = crawl.pipelines[4]
    storage_pipeline.max_depth = max_depth
    stopping = StoppingPipeline(
        crawl.broker,
        StopConditions(max_nodes=max_nodes, max_duration=60, no_progress_timeout=60),
    )
    crawl.broker.subscribe(stopping, [NodeAddedEvent, PageFetchedEvent, StopCrawlEvent])
    crawl.pipelines.append(stopping)
    await crawl.start()
    await asyncio.sleep(0.05)
    await crawl.add_seed("a")
    try:
        await wait_until(lambda: stopping.stopped, timeout=3.0)
        await asyncio.sleep(0.2)
    finally:
        await crawl.stop()
    return crawl, stopping


async def test_max_nodes_counts_fetched_pages():
    crawl, stopping = await _run_stopping_crawl(max_nodes=3, max_depth=10)

    assert crawl.site.fetched == ["a", "b", "c"]
    assert stopping.node_count == 3


async def test_max_depth_stops_admission_not_the_crawl():
    crawl, stopping = await _run_stopping_crawl(max_nodes=100, max_depth=2)

    assert crawl.site.fetched == ["a", "b", "c"]  # depth 0, 1, 2; "d" never admitted
    assert not stopping.stopped or stopping.node_count == 3


async def test_decision_events_keep_values_after_rescore():
    """A decision event records the values at decision time, not the live link's."""
    broker = EventBroker()
    link = Link("http://x/a", "a", "ctx")
    link.score, link._nlp_score = 7, 0.4
    event = HighScoreLinksEvent(
        "1", node=None, links=[link],
        records=[{"url": link.url, "score": 7, "nlp_score": 0.4}],
    )
    await broker.emit(event)
    other = StopCrawlEvent("NO_PROGRESS", 1, 0, 0.0)
    await broker.emit(other)
    link.score = 99  # scoring retry mutates the shared object
    assert event.records[0]["score"] == 7
    assert 0 < event.seq < other.seq


async def test_scoring_runs_under_a_trace_bound_to_the_node():
    """Trace events emitted while scoring a node carry a non-empty trace_id."""
    from traceability import get_trace

    seen = []

    class TraceProbe(FixedRelevance):
        async def score_links(self, links, parent):
            seen.append(get_trace())
            return await super().score_links(links, parent)

    broker, storage = EventBroker(), Storage()
    domain = Domain("synthetic", BASE_URL, ".//a")
    scoring = make_scoring(broker, TraceProbe(0.5), FixedLlm())
    broker.subscribe(scoring, [NodeAddedEvent])
    node = seed_node(storage, domain, "page")
    node.set_links([Link(f"{BASE_URL}/c{i}", f"c{i}", "") for i in range(3)])
    node.update_state()

    tasks = [asyncio.create_task(broker.start()), asyncio.create_task(scoring.start())]
    await broker.emit(NodeAddedEvent(correlation_id=str(node.get_id()), node=node))
    await wait_until(lambda: bool(seen), 2.0)
    await broker.emit(StopCrawlEvent("NO_PROGRESS", 1, 0, 0.0))
    await stop_all(tasks)

    assert seen and seen[0][0] and seen[0][1] == str(node.get_id())
