"""Everything an offline crawl swaps in for the outside world."""

import os
from dataclasses import dataclass
from pathlib import Path

from benchmark.graph import FrozenGraph, GraphFetcher
from config.runtime_config import RuntimeConfig

from .scripted_llm import ScriptedLlm
from .site_script import RateLimitedFetcher, SiteScript

OFFLINE_ENV_VAR = "CRAWLVIZ_OFFLINE"
OFFLINE_EMBEDDING_BACKEND = "hashing"
OFFLINE_GRAPH = Path(__file__).resolve().parent.parent / "benchmark" / "data" / "isi.json"
SITE_SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"
_TRUTHY = {"1", "true", "yes", "on"}


def is_offline() -> bool:
    return os.environ.get(OFFLINE_ENV_VAR, "").strip().lower() in _TRUTHY


@dataclass
class OfflineSession:
    """The doubles for one crawl, and the config that selects hashing embeddings."""

    config: RuntimeConfig
    llm: ScriptedLlm
    fetcher: GraphFetcher | RateLimitedFetcher


def find_site_script(template_name: str | None) -> SiteScript | None:
    """The script in ``SITE_SCRIPTS_DIR`` named after the blueprint, if there is one."""
    if template_name is None:
        return None
    path = SITE_SCRIPTS_DIR / f"{Path(template_name).stem}.json"
    return SiteScript.load(path) if path.is_file() else None


def build_offline_session(
    config: RuntimeConfig, template_name: str | None = None
) -> OfflineSession:
    """Pair ``config`` (switched to hashing embeddings) with a scripted LLM and a frozen site.

    A blueprint with a site script (``offline/scripts/<blueprint>.json``) gets the scripted
    synthetic site and the script's settings; any other blueprint gets the frozen ISI graph.
    """
    script = find_site_script(template_name)
    if script is None:
        fetcher: GraphFetcher | RateLimitedFetcher = FrozenGraph.load(OFFLINE_GRAPH).fetcher()
    else:
        fetcher = script.build_fetcher()
        config = script.apply_config(config)
    config.embeddings.backend = OFFLINE_EMBEDDING_BACKEND
    return OfflineSession(config=config, llm=ScriptedLlm(), fetcher=fetcher)
