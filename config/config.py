"""Central configuration for the CrawlViz backend.

Everything here is a plain module-level constant so the rest of the
codebase can do ``from config import X`` without carrying a settings
object around. Filesystem roots are ``pathlib.Path`` instances; anything
that plausibly needs to differ between environments (currently just the
CORS origin) can be overridden with an environment variable.
"""

import os
from pathlib import Path

from crawlviz.llm import default_llm_endpoints
from crawlviz.nlp import default_composite_weights

# =========================================================================
# PATHS
# =========================================================================
BASE_DIR: Path = Path(__file__).resolve().parent.parent
EXPORT_DIR_NAME = "export"
ITEMS_DB_NAME = "items.db"
EXPORT_PATH: Path = BASE_DIR / EXPORT_DIR_NAME
ITEMS_DB_PATH: Path = BASE_DIR / ITEMS_DB_NAME
TEMPLATES_DIR: Path = BASE_DIR / "templates"

# =========================================================================
# GENERAL
# =========================================================================
DEBUG: bool = True

# API server CORS. A comma-separated CRAWLVIZ_CORS_ORIGINS overrides the
# Vite dev-server default, e.g. for deploying the frontend elsewhere.
CORS_ORIGINS: list[str] = os.environ.get("CRAWLVIZ_CORS_ORIGINS", "http://localhost:5173").split(
    ","
)
# Regex for additional allowed origins (Vite falls back to 5174, 5175... when
# 5173 is taken). Any local port by default. Set CRAWLVIZ_CORS_ORIGIN_REGEX to
# an empty string to allow only CRAWLVIZ_CORS_ORIGINS, e.g. for a deployment.
CORS_ORIGIN_REGEX: str | None = (
    os.environ.get("CRAWLVIZ_CORS_ORIGIN_REGEX", r"https?://(localhost|127\.0\.0\.1)(:\d+)?")
    or None
)

# Host names the API answers to. A request whose Host header names anything else is refused,
# which stops DNS rebinding (a page on evil.example resolving to 127.0.0.1 and reading the API
# as its own origin). CRAWLVIZ_ALLOWED_HOSTS adds comma-separated names, without ports, for a
# deployment behind a proxy.
LOCAL_HOST_NAMES: tuple[str, ...] = ("localhost", "127.0.0.1", "[::1]")
ALLOWED_HOSTS: tuple[str, ...] = (
    *LOCAL_HOST_NAMES,
    *(
        name.strip().lower()
        for name in os.environ.get("CRAWLVIZ_ALLOWED_HOSTS", "").split(",")
        if name.strip()
    ),
)

# =========================================================================
# NLP EMBEDDINGS
# =========================================================================
EMBEDDING_BACKEND: str = "sentence_transformers"
EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
SPACE_STORE_DIR: str = ".space_store"

# How often (and at what buffer size) the semantic space is grown from
# newly-scored links -- see nlp/space_updater.py. Report section 0.12.3
# ("Raffinement iteratif de la base semantique").
FLUSH_INTERVAL_SECONDS: float = 60.0
FLUSH_THRESHOLD: int = 50
BUFFER_MAX_SIZE: int = 500

# =========================================================================
# POLITENESS
# =========================================================================
# Identify the crawler honestly. The project page is the default contact; an operator
# crawling live sites should set their own (a web or email address, see config/user_agent.py).
USER_AGENT: str = "CrawlViz/1.0 (+https://github.com/omarbounawarapy/crawlviz)"
RESPECT_ROBOTS: bool = True
# Largest page body read, after decompression; a bigger response is refused.
MAX_RESPONSE_BYTES: int = 5 * 1024 * 1024

# =========================================================================
# SCORING CASCADE (REPORT SECTION 0.13 "EVALUATION MULTI-ETAPES")
# =========================================================================
# A link's NLP similarity score buckets it into low / mid / high confidence.
NLP_LOW_SCORE_THRESHOLD: float = 0.20
NLP_HIGH_SCORE_THRESHOLD: float = 0.75

# Fraction of the "high confidence" bucket that still gets an LLM call
# rather than being trusted outright -- this is the cascade's cost saving.
HIGH_SCORE_LLM_FRACTION: float = 0.30
# Of that LLM-bound slice, the fraction filled by random sampling (for
# bias correction, report section 0.15.2) rather than top-ranked links.
HIGH_SCORE_RANDOM_FRACTION: float = 0.30
# Fraction of the "low confidence" bucket kept anyway, for exploration.
LOW_SCORE_SAMPLE_FRACTION: float = 0.01

# Percentile bucketing: NLP scores from a sentence-embedding model cluster in
# a narrow band (median ~0.4, max ~0.6), so the fixed thresholds above never
# separate anything. When True, "low"/"high" are the given percentiles of each
# node's own link scores instead (the absolute thresholds remain as the
# fallback for batches smaller than PERCENTILE_MIN_LINKS).
NLP_PERCENTILE_BUCKETING: bool = True
NLP_LOW_PERCENTILE: float = 20.0
NLP_HIGH_PERCENTILE: float = 75.0
PERCENTILE_MIN_LINKS: int = 10
# Hard cap on links sent to the LLM per node (keeps one prompt well under
# provider token limits). Overflow is kept, ranked by NLP score only.
MAX_LLM_LINKS_PER_NODE: int = 60

# Composite NLP score weights (nlp/feature_extractor signals); the default values live
# with the scorer in crawlviz.nlp.
NLP_COMPOSITE_WEIGHTS: dict[str, float] = default_composite_weights()

DEFAULT_PRIORITY_STRATEGY: str = "balanced"

# Stop conditions a blueprint gets when it does not set its own: a crawl that ends on
# its own after a modest, bounded amount of work (ETH-1).
DEFAULT_MAX_NODES: int = 500
DEFAULT_MAX_DEPTH: int = 5
DEFAULT_MAX_DURATION_SECONDS: float = 3600.0

# =========================================================================
# LLM PROVIDERS
# =========================================================================
# Request URL per provider lives with the LLM adapters; re-exported for config users.
LLM_DEFAULT_ENDPOINTS: dict[str, str] = default_llm_endpoints()

# =========================================================================
# EXPORT
# =========================================================================
EXPORT_BATCH_SIZE: int = 1
