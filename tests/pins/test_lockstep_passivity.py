"""Extra components hear the run, and observers that change nothing leave the crawl unchanged."""
import json
from pathlib import Path
from typing import Any

import pytest
from pin_crawl import use_hashing_embeddings
from pin_doubles import RecordingLlm, ScriptedLlm
from pin_paths import REPO_ROOT

from benchmark import FrozenGraph, run_policy, synthetic_graph
from benchmark.llm_cache import CachedLlm
from benchmark.runner import RunResult, run_cascade
from events import RequestStartedEvent, StorageNodeUpdatedEvent

BLUEPRINT = REPO_ROOT / "templates" / "isi.json"
ISI_GRAPH = REPO_ROOT / "benchmark" / "data" / "isi.json"
SYNTHETIC_PAGES = 60
SYNTHETIC_SEED = 1
BASELINE_PAGES = 200
BASELINE_BUDGET = 30
CASCADE_BUDGET = 20
EXTRA_COMPONENT_BUDGET = 10


class Listener:
    """An extra component that hears one event type and notes it."""

    def __init__(self, event_type: type) -> None:
        self.heard: list[Any] = []
        self.handlers = {event_type: self.put}

    async def start(self) -> None:
        pass

    async def put(self, event: Any) -> None:
        self.heard.append(event)


async def _cascade(
    work_dir: Path, graph: FrozenGraph, budget: int, extra_components: list[Listener] | None = None
) -> tuple[RunResult, list[str]]:
    """A cascade run on ``graph`` in its own folder; returns the result and the prompts sent."""
    blueprint = json.loads(BLUEPRINT.read_text())
    expansion = {**blueprint["expansion"], "llm_type": "groq", "llm_model": "m"}
    llm = RecordingLlm(ScriptedLlm())
    run_dir = work_dir / f"run{len(list(work_dir.iterdir()))}"
    result = await run_cascade(
        graph, budget, 0, CachedLlm(llm, run_dir / "cache.jsonl", scope="rep0"),
        blueprint["extraction"], expansion, blueprint["scoring"]["strategy"], ("groq", "m"),
        run_dir / "space", extra_components=extra_components or (),
    )
    return result, [request["prompt"] for request in llm.requests]


def _requested(listener: Listener, pages: int) -> list[str]:
    # The request after the budget starts but is never served, so it is cut off.
    return [event.url.rsplit("/", 1)[1] for event in listener.heard][:pages]


async def test_extra_components_hear_the_run_they_are_given_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = synthetic_graph(n_pages=SYNTHETIC_PAGES, seed=SYNTHETIC_SEED)
    listener = Listener(RequestStartedEvent)
    result = await run_policy(graph, "bfs", EXTRA_COMPONENT_BUDGET, extra_components=[listener])
    assert _requested(listener, EXTRA_COMPONENT_BUDGET) == result.visited

    use_hashing_embeddings(monkeypatch)
    listener = Listener(RequestStartedEvent)
    result, _ = await _cascade(tmp_path, graph, EXTRA_COMPONENT_BUDGET, [listener])
    assert result.health.valid
    assert _requested(listener, EXTRA_COMPONENT_BUDGET) == result.visited


# StorageNodeUpdatedEvent is emitted just after a fetched node becomes ready,
# and nothing in the benchmark subscribes to it. A listener on it adds only a
# dispatch task; the run must visit the same pages and send the same prompts.
async def test_an_idle_listener_does_not_change_a_baseline_run() -> None:
    graph = synthetic_graph(n_pages=BASELINE_PAGES, seed=0)
    alone = await run_policy(graph, "anchor_lexical", BASELINE_BUDGET)
    observed = await run_policy(
        graph, "anchor_lexical", BASELINE_BUDGET,
        extra_components=[Listener(StorageNodeUpdatedEvent)],
    )
    assert observed.visited == alone.visited


async def test_an_idle_listener_does_not_change_a_cascade_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_hashing_embeddings(monkeypatch)
    graph = FrozenGraph.load(ISI_GRAPH)
    alone, alone_prompts = await _cascade(tmp_path, graph, CASCADE_BUDGET)
    observed, observed_prompts = await _cascade(
        tmp_path, graph, CASCADE_BUDGET, [Listener(StorageNodeUpdatedEvent)]
    )
    assert alone.health.valid and observed.health.valid
    assert observed.visited == alone.visited
    assert observed_prompts == alone_prompts
