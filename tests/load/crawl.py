"""A real ``Crawler`` run on the synthetic site, measured.

Only the outside world is replaced, as in offline mode (``crawlviz.offline``): the site is
a ``SiteScript`` served by a fetcher with no network, the LLM is ``ScriptedLlm`` and the
embeddings are hashed. Every stage, queue and the event broker are the production ones.
"""

import asyncio
import math
import socket
import time
from dataclasses import dataclass
from pathlib import Path

from config.paths import RuntimePaths
from config.runtime_config import default_runtime_config
from core import Crawler
from crawlviz.offline import ScriptedLlm
from tests.load.event_counter import EventCounter
from tests.load.loop_lag import LoopLagMonitor
from tests.load.measurement import Measurement, get_peak_rss_mb
from tests.load.site import (
    LOAD_BLUEPRINT,
    OUT_DEGREE,
    SITE_HEADROOM,
    build_site_script,
    write_load_blueprint,
)

EMBEDDING_BACKEND = "hashing"
LOAD_RANDOM_SEED = 0
FETCH_WORKERS = 8
SCORE_WORKERS = 4
# A crawl that fetches or stores nothing for this long has run out of links to follow.
NO_PROGRESS_SECONDS = 60.0
REACHED_PAGE_BUDGET = "MAX_NODES_REACHED"


class CrawlEndedEarlyError(RuntimeError):
    """The crawl stopped for a reason other than reaching its page budget.

    A run that did not fetch the pages it was asked to has measured nothing comparable, so
    the harness fails it and never reports it as a fast or slow result.
    """


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass(frozen=True)
class LoadOptions:
    """What a load crawl may vary; the defaults are the harness's own.

    ``site_headroom`` is how many times the page budget the site has pages: the cascade
    drops some links, so a site of exactly the budget has pages no kept link reaches.
    """

    no_progress_seconds: float = NO_PROGRESS_SECONDS
    out_degree: int = OUT_DEGREE
    site_headroom: float = SITE_HEADROOM


async def run_load_crawl(
    page_count: int,
    work_dir: Path,
    timeout_seconds: float,
    options: LoadOptions = LoadOptions(),  # noqa: B008 (frozen, so shared safely)
) -> Measurement:
    """Crawl to a budget of ``page_count`` pages with the real ``Crawler`` and measure the run.

    The clock covers ``Crawler.start()`` only: building the site and the blueprint is set-up.
    A crawl still running after ``timeout_seconds`` raises ``TimeoutError``, and one that
    stops before its budget raises ``CrawlEndedEarlyError`` naming the reason.
    """
    site_pages = math.ceil(page_count * options.site_headroom)
    script = build_site_script(site_pages, FETCH_WORKERS, SCORE_WORKERS, options.out_degree)
    config = script.apply_config(default_runtime_config())
    config.embeddings.backend = EMBEDDING_BACKEND
    fetcher = script.build_fetcher()
    templates_dir = work_dir / "templates"
    write_load_blueprint(templates_dir, page_count, options.no_progress_seconds)
    crawler = Crawler(
        LOAD_BLUEPRINT,
        config=config,
        paths=RuntimePaths.under(work_dir, templates_dir=templates_dir),
        seed=LOAD_RANDOM_SEED,
        ui_port=_free_port(),
        llm=ScriptedLlm(),
        fetcher=fetcher,
    )
    counter = EventCounter()
    crawler.event_broker.subscribe(counter, counter.event_types)

    async with LoopLagMonitor() as lag:
        started = time.perf_counter()
        await asyncio.wait_for(crawler.start(), timeout_seconds)
        wall_seconds = time.perf_counter() - started

    fetched_pages = len(fetcher.fetched)
    if counter.stop_reason != REACHED_PAGE_BUDGET:
        raise CrawlEndedEarlyError(
            f"the crawl stopped with {counter.stop_reason} after {fetched_pages} of "
            f"{page_count} pages; the site ran out of links the crawler would follow"
        )
    summary = lag.summary()
    return Measurement(
        page_budget=page_count,
        fetched_pages=fetched_pages,
        wall_seconds=wall_seconds,
        pages_per_second=fetched_pages / wall_seconds,
        peak_rss_mb=get_peak_rss_mb(),
        loop_lag_samples=summary.samples,
        loop_lag_p50_ms=summary.p50_ms,
        loop_lag_p99_ms=summary.p99_ms,
        loop_lag_max_ms=summary.max_ms,
        stop_reason=counter.stop_reason,
        event_counts=dict(counter.counts),
    )
