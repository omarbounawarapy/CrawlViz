"""The synthetic site and the blueprint of a load run.

The site is ``SiteScript`` data (``crawlviz.offline.site_script``), the same synthetic
graph the long offline demo serves, only larger. Its blueprint is the long demo's with a
page budget of ``page_count`` and limits that cannot stop the crawl first.

Why ``OUT_DEGREE`` is 12 and not the demo's 8: the scoring cascade buckets a page's links
by percentile only when the page has ``percentile_min_links`` (10) links or more. With
fewer it uses fixed cut-offs, and on this site every link of the seed page scores under the
low cut-off. Low links are dropped except for a 1% sample, which keeps none of 8. The
frontier is then empty after the first page and the crawl waits for its no-progress
timeout. The harness therefore uses a degree that stays on the percentile path, and it
fails a crawl that ends before its page budget (``tests.load.crawl.CrawlEndedEarlyError``).
"""

import json
from pathlib import Path
from typing import Any

from config import TEMPLATES_DIR
from crawlviz.offline.site_script import SiteScript, SiteSpec

DEMO_BLUEPRINT = "offline_demo_long.json"
LOAD_BLUEPRINT = "load_site.json"
SITE_SEED = 7
OUT_DEGREE = 12
# The site has this many times the page budget (see ``LoadOptions.site_headroom``).
SITE_HEADROOM = 3.0
RELEVANT_FRACTION = 0.15

# Limits a load run must not hit before its page budget: a depth no random graph of this
# degree reaches, and one hour of run time.
UNREACHED_DEPTH = 1000
LOAD_MAX_DURATION_SECONDS = 3600


def build_site_script(
    site_pages: int, fetch_workers: int, score_workers: int, out_degree: int = OUT_DEGREE
) -> SiteScript:
    """A site of ``site_pages`` pages that never answers 429, with no politeness delay.

    The delay is off because the harness measures the crawler, not the wait a real site
    would impose; the pins and the demo keep the real defaults.
    """
    return SiteScript(
        schema_version=1,
        site=SiteSpec(
            n_pages=site_pages,
            out_degree=out_degree,
            relevant_fraction=RELEVANT_FRACTION,
            seed=SITE_SEED,
        ),
        rate_limit_episodes=[],
        config={
            "fetch": {"min_delay": 0.0, "jitter_max": 0.0},
            "pipelines": {
                "fetch": {"workers": fetch_workers},
                "score": {"workers": score_workers},
            },
        },
    )


def write_load_blueprint(
    templates_dir: Path, page_count: int, no_progress_timeout_seconds: float
) -> None:
    """``LOAD_BLUEPRINT`` in ``templates_dir``: the long demo's, with a ``page_count`` budget."""
    # Any: a blueprint is JSON read from disk.
    blueprint: dict[str, Any] = json.loads(
        (Path(TEMPLATES_DIR) / DEMO_BLUEPRINT).read_text(encoding="utf-8")
    )
    blueprint["stop_conditions"].update(
        max_nodes=page_count,
        max_depth=UNREACHED_DEPTH,
        max_duration=LOAD_MAX_DURATION_SECONDS,
        no_progress_timeout=no_progress_timeout_seconds,
    )
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / LOAD_BLUEPRINT).write_text(json.dumps(blueprint), encoding="utf-8")
