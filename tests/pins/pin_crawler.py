"""A crawl through the real ``Crawler``, run offline, with what a pin compares recorded.

``pin_crawl`` pins the cascade through ``benchmark.runner``; this module pins the
composition root (``core/crawler.py``, ``core/stages.py``). The same blueprint
(``templates/offline_demo.json``) is crawled the way ``CRAWLVIZ_OFFLINE=1`` does
it: ``build_offline_session`` supplies the frozen ISI site, ``ScriptedLlm`` and
hashing embeddings.

Unlike the runner, ``Crawler`` has no lockstep: stages run as concurrent tasks and
the crawl ends when a stop event races the next fetch. So only what does not depend
on that race is recorded:

* ``composition``: every stage the registry builds, in start order, and the
  consumers of every event type in the order the broker dispatches them,
* ``fetch_order``: the first ``budget`` pages fetched with one fetch worker (fetches
  already under way when the stop fires finish too, so the crawl may fetch one more),
* ``llm_requests``: the first ``LLM_PROMPTS_PINNED`` prompts, in order (the expansion
  and the first scoring call; a later call may or may not start before the stop).
"""

import asyncio
import json
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pin_doubles import RecordingLlm
from pin_paths import REPO_ROOT

from config.paths import RuntimePaths
from config.runtime_config import default_runtime_config
from core import Crawler
from offline import build_offline_session

BLUEPRINT_NAME = "offline_demo.json"
PIN_RANDOM_SEED = 0
# One worker per stage that fetches or scores keeps the visit order a function of the scores.
PIN_WORKERS = 1
CRAWL_TIMEOUT_SECONDS = 60
LLM_PROMPTS_PINNED = 2


@dataclass
class CrawlerRun:
    composition: list[dict[str, Any]]
    fetch_order: list[dict[str, Any]]
    llm_requests: list[dict[str, str]]
    fetched_total: int
    llm_calls_total: int


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_blueprint(templates_dir: Path, max_nodes: int) -> None:
    """The offline demo blueprint with a small page budget, in ``templates_dir``."""
    blueprint = json.loads((REPO_ROOT / "templates" / BLUEPRINT_NAME).read_text(encoding="utf-8"))
    blueprint["stop_conditions"]["max_nodes"] = max_nodes
    templates_dir.mkdir()
    (templates_dir / BLUEPRINT_NAME).write_text(json.dumps(blueprint), encoding="utf-8")


def describe_composition(crawler: Crawler) -> list[dict[str, Any]]:
    """Stages in start order, then each event type with its consumers in dispatch order."""
    names = {id(stage): key for key, stage in crawler._pipelines.items()}
    composition: list[dict[str, Any]] = [
        {"stage": key, "class": type(stage).__name__} for key, stage in crawler._pipelines.items()
    ]
    for event_type, consumers in crawler.event_broker.registry.registry.items():
        composition.append(
            {
                "event": event_type.__name__,
                "consumers": [
                    names.get(id(consumer), type(consumer).__name__) for consumer in consumers
                ],
            }
        )
    return composition


async def run_pin_crawler(budget: int, work_dir: Path) -> CrawlerRun:
    """Crawl ``budget`` pages of the frozen ISI site through ``Crawler.start``."""
    session = build_offline_session(default_runtime_config())
    llm = RecordingLlm(session.llm)
    templates_dir = work_dir / "templates"
    write_blueprint(templates_dir, budget)
    crawler = Crawler(
        BLUEPRINT_NAME,
        config=session.config,
        paths=RuntimePaths.under(work_dir, templates_dir=templates_dir),
        seed=PIN_RANDOM_SEED,
        fetch_concurrency=PIN_WORKERS,
        scoring_concurrency=PIN_WORKERS,
        ui_port=_free_port(),
        llm=llm,
        fetcher=session.fetcher,
    )
    await asyncio.wait_for(crawler.start(), CRAWL_TIMEOUT_SECONDS)
    fetched = session.fetcher.fetched
    return CrawlerRun(
        composition=describe_composition(crawler),
        fetch_order=[{"n": n, "page": page} for n, page in enumerate(fetched[:budget], start=1)],
        llm_requests=llm.requests[:LLM_PROMPTS_PINNED],
        fetched_total=len(fetched),
        llm_calls_total=len(llm.requests),
    )
