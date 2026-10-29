"""Everything an offline crawl swaps in for the outside world."""
import os
from dataclasses import dataclass
from pathlib import Path

from benchmark.graph import FrozenGraph, GraphFetcher
from config.runtime_config import RuntimeConfig

from .scripted_llm import ScriptedLlm

OFFLINE_ENV_VAR = "CRAWLVIZ_OFFLINE"
OFFLINE_EMBEDDING_BACKEND = "hashing"
OFFLINE_GRAPH = Path(__file__).resolve().parent.parent / "benchmark" / "data" / "isi.json"
_TRUTHY = {"1", "true", "yes", "on"}


def is_offline() -> bool:
    return os.environ.get(OFFLINE_ENV_VAR, "").strip().lower() in _TRUTHY


@dataclass
class OfflineSession:
    """The doubles for one crawl, and the config that selects hashing embeddings."""

    config: RuntimeConfig
    llm: ScriptedLlm
    fetcher: GraphFetcher


def build_offline_session(config: RuntimeConfig) -> OfflineSession:
    """Switch ``config`` to hashing embeddings and pair it with a frozen site and a scripted LLM."""
    config.embeddings.backend = OFFLINE_EMBEDDING_BACKEND
    graph = FrozenGraph.load(OFFLINE_GRAPH)
    return OfflineSession(config=config, llm=ScriptedLlm(), fetcher=graph.fetcher())
