"""A crawl on a frozen graph, run offline, with everything a pin compares recorded.

The crawl is ``benchmark.runner.run_cascade``: the production pipelines, the
real ``NLPService`` and ``ScoringService``, lockstep so the visit order does not
depend on timing. Only the outside world is replaced:

* the web by ``FrozenGraph`` (served as HTML by its own fetcher),
* the embedding model by ``HashingEmbeddingEngine`` (a config switch),
* the LLM by ``ScriptedLlm`` behind ``CachedLlm``, the wrapper the benchmark uses.

Four things are recorded, one golden file each:

* ``fetch_order``: the pages in the order they were fetched,
* ``link_scores``: every link's NLP score, LLM score and priority as decided,
* ``llm_requests``: the prompt of every LLM call, in order,
* ``wire_messages``: every message the UI bridge broadcast.
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pin_doubles import RecordingLlm, ScriptedLlm
from pin_observer import PinObserver
from pin_paths import REPO_ROOT

from benchmark import runner
from benchmark.graph import FrozenGraph
from benchmark.llm_cache import CachedLlm
from config import runtime_config

PIN_RANDOM_SEED = 0
PIN_SCOPE = "pins"
PIN_PROVIDER = "pin-provider"
PIN_MODEL = "pin-model"
BLUEPRINT_PATH = REPO_ROOT / "templates" / "isi.json"


@dataclass
class PinRun:
    fetch_order: list[dict[str, Any]]
    link_scores: list[dict[str, Any]]
    llm_requests: list[dict[str, str]]
    wire_messages: list[dict[str, Any]]


def use_hashing_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default runtime config, with the hashing embedding engine."""
    real = runtime_config.default_runtime_config

    def hashing_config() -> Any:
        config = real()
        config.embeddings.backend = "hashing"
        return config

    monkeypatch.setattr(runtime_config, "default_runtime_config", hashing_config)


async def run_pin_crawl(
    graph: FrozenGraph,
    budget: int,
    work_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    observed: bool = True,
) -> PinRun:
    """Fetch ``budget`` pages of ``graph`` and return what the pins compare.

    ``work_dir`` receives the LLM cache and the semantic-space store; give each
    crawl its own empty folder. The config patch lives only for this call, so one
    test can run several crawls. With ``observed=False`` the observer is not
    attached, so ``link_scores`` and ``wire_messages`` come back empty; the
    passivity test compares that run with an observed one.
    """
    observer = PinObserver(budget)
    llm = RecordingLlm(CachedLlm(ScriptedLlm(), work_dir / "llm_cache.jsonl", scope=PIN_SCOPE))
    blueprint = json.loads(BLUEPRINT_PATH.read_text(encoding="utf-8"))
    expansion = {**blueprint["expansion"], "llm_type": PIN_PROVIDER, "llm_model": PIN_MODEL}

    with monkeypatch.context() as patch:
        use_hashing_embeddings(patch)
        result = await runner.run_cascade(
            graph, budget, PIN_RANDOM_SEED, llm, blueprint["extraction"], expansion,
            blueprint["scoring"]["strategy"], (PIN_PROVIDER, PIN_MODEL), work_dir / "space_store",
            extra_components=[observer] if observed else [],
        )

    assert result.health.valid, result.health.problems
    return PinRun(
        fetch_order=[{"n": n, "page": page} for n, page in enumerate(result.visited, start=1)],
        link_scores=observer.link_scores(),
        llm_requests=llm.requests,
        wire_messages=observer.wire_messages(),
    )
