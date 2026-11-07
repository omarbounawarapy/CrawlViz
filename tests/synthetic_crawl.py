"""A real ``Crawler`` on a small synthetic site, for tests of how a crawl ends.

Only the outside world is replaced, as in offline mode: the site is served with no network,
the LLM is ``ScriptedLlm`` and the embeddings are hashed. Every stage, queue and the event
broker are the production ones. The site and blueprint are the load harness's
(``tests/load/site.py``), so a test here and a load run crawl the same graph.
"""

import math
import socket
from dataclasses import dataclass
from pathlib import Path

from config.paths import RuntimePaths
from config.runtime_config import RuntimeConfig, default_runtime_config
from core import Crawler
from crawlviz.events import StopCrawlEvent
from crawlviz.offline import ScriptedLlm
from crawlviz.offline.site_script import RateLimitedFetcher
from tests.load.site import (
    LOAD_BLUEPRINT,
    OUT_DEGREE,
    SITE_HEADROOM,
    build_site_script,
    write_load_blueprint,
)

FETCH_WORKERS = 8
SCORE_WORKERS = 4
NO_PROGRESS_SECONDS = 60.0
NO_STOP_REASON = "NOT_STOPPED"
# Short, so a crawl that is cut off instead of stopping shows it within the test's patience.
SHUTDOWN_GRACE_SECONDS = 0.2


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class StopWatcher:
    """Remembers why the crawl stopped."""

    def __init__(self) -> None:
        self.stop_reason = NO_STOP_REASON

    @property
    def event_types(self) -> tuple[type, ...]:
        return (StopCrawlEvent,)

    async def put(self, event: object) -> None:
        if isinstance(event, StopCrawlEvent):
            self.stop_reason = event.reason


@dataclass
class SyntheticCrawl:
    """A built crawl, not yet started: ``await crawl.crawler.start()`` runs it."""

    crawler: Crawler
    fetcher: RateLimitedFetcher
    watcher: StopWatcher

    @property
    def fetched_pages(self) -> int:
        return len(self.fetcher.fetched)


@dataclass(frozen=True)
class CrawlOptions:
    """What a test may vary about the crawl; the defaults are the harness's own."""

    debug_enabled: bool = True
    out_degree: int = OUT_DEGREE
    no_progress_seconds: float = NO_PROGRESS_SECONDS
    fetch_queue_size: int | None = None
    shutdown_grace_seconds: float = SHUTDOWN_GRACE_SECONDS


def build_synthetic_crawl(
    work_dir: Path,
    page_budget: int,
    options: CrawlOptions = CrawlOptions(),  # noqa: B008
) -> SyntheticCrawl:
    """A crawl of ``page_budget`` pages on a site three times that size."""
    site_pages = math.ceil(page_budget * SITE_HEADROOM)
    script = build_site_script(site_pages, FETCH_WORKERS, SCORE_WORKERS, options.out_degree)
    config: RuntimeConfig = script.apply_config(default_runtime_config())
    config.embeddings.backend = "hashing"
    config.observability.debug_enabled = options.debug_enabled
    config.run.shutdown_grace = options.shutdown_grace_seconds
    config.pipelines.fetch.max_queue_size = options.fetch_queue_size
    templates_dir = work_dir / "templates"
    write_load_blueprint(templates_dir, page_budget, options.no_progress_seconds)
    fetcher = script.build_fetcher()
    crawler = Crawler(
        LOAD_BLUEPRINT,
        config=config,
        paths=RuntimePaths.under(work_dir, templates_dir=templates_dir),
        seed=0,
        ui_port=_free_port(),
        llm=ScriptedLlm(),
        fetcher=fetcher,
    )
    watcher = StopWatcher()
    crawler.event_broker.subscribe(watcher, watcher.event_types)
    return SyntheticCrawl(crawler, fetcher, watcher)
