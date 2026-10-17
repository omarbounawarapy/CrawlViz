"""Extra components hear the run, and observers that change nothing leave the crawl unchanged."""
import json
import re
import zlib
from pathlib import Path

from benchmark import FrozenGraph, run_policy, synthetic_graph
from benchmark.llm_cache import CachedLlm
from benchmark.runner import run_cascade
from events import RequestStartedEvent, StorageNodeUpdatedEvent

BLUEPRINT = Path("templates/isi.json")
ISI_GRAPH = Path("benchmark/data/isi.json")


class _Listener:
    """An extra component that hears one event type and notes it."""

    def __init__(self, event_type):
        self.heard: list[object] = []
        self.handlers = {event_type: self.put}

    async def start(self):
        pass

    async def put(self, event):
        self.heard.append(event)


class _ChecksumLlm:
    """Scores each candidate by a checksum of its URL: arbitrary, repeatable, rarely tied."""

    def __init__(self):
        self.prompts: list[str] = []

    async def send(self, ctx):
        self.prompts.append(ctx.get_prompt())
        match = re.search(r"CANDIDATES:\n(\[.*?\])\n", ctx.get_prompt(), re.DOTALL)
        if not match:
            return {"target": "t", "descriptions": ["diabetes insulin glucose", "pancreas care"]}
        urls = [c["url"] for c in json.loads(match.group(1))]
        return {"results": [
            {"url": u, "score": zlib.crc32(u.encode()) % 100, "relevance_type": "direct", "expansions": []}
            for u in urls
        ]}


def _hashing_embeddings(monkeypatch):
    import config.runtime_config as rc

    real = rc.default_runtime_config

    def patched():
        cfg = real()
        cfg.embeddings.backend = "hashing"
        return cfg

    monkeypatch.setattr(rc, "default_runtime_config", patched)


async def _cascade(tmp_path, graph, budget, extra_components=()):
    bp = json.loads(BLUEPRINT.read_text())
    expansion = {**bp["expansion"], "llm_type": "groq", "llm_model": "m"}
    llm = _ChecksumLlm()
    work = tmp_path / f"run{len(list(tmp_path.iterdir()))}"
    result = await run_cascade(
        graph, budget, 0, CachedLlm(llm, work / "cache.jsonl", scope="rep0"), bp["extraction"],
        expansion, bp["scoring"]["strategy"], ("groq", "m"), work / "space",
        extra_components=extra_components,
    )
    return result, llm.prompts


def _requested(listener: _Listener, pages: int) -> list[str]:
    # The request after the budget starts but is never served, so it is cut off.
    return [event.url.rsplit("/", 1)[1] for event in listener.heard][:pages]


async def test_extra_components_hear_the_run_they_are_given_to(tmp_path, monkeypatch):
    listener = _Listener(RequestStartedEvent)
    result = await run_policy(synthetic_graph(n_pages=60, seed=1), "bfs", 10, extra_components=[listener])
    assert _requested(listener, 10) == result.visited

    _hashing_embeddings(monkeypatch)
    listener = _Listener(RequestStartedEvent)
    result, _ = await _cascade(tmp_path, synthetic_graph(n_pages=60, seed=1), 10, [listener])
    assert result.health.valid
    assert _requested(listener, 10) == result.visited


# StorageNodeUpdatedEvent is emitted just after a fetched node becomes ready,
# and nothing in the benchmark subscribes to it. A listener on it adds only a
# dispatch task; the run must visit the same pages and send the same prompts.
async def test_an_idle_listener_does_not_change_a_baseline_run():
    graph = synthetic_graph(n_pages=200, seed=0)
    alone = await run_policy(graph, "anchor_lexical", 30)
    observed = await run_policy(
        graph, "anchor_lexical", 30, extra_components=[_Listener(StorageNodeUpdatedEvent)]
    )
    assert observed.visited == alone.visited


async def test_an_idle_listener_does_not_change_a_cascade_run(tmp_path, monkeypatch):
    _hashing_embeddings(monkeypatch)
    graph = FrozenGraph.load(ISI_GRAPH)
    alone, alone_prompts = await _cascade(tmp_path, graph, 20)
    observed, observed_prompts = await _cascade(
        tmp_path, graph, 20, [_Listener(StorageNodeUpdatedEvent)]
    )
    assert alone.health.valid and observed.health.valid
    assert observed.visited == alone.visited
    assert observed_prompts == alone_prompts
