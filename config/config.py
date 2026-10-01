"""Central configuration for the CrawlViz backend.

Everything here is a plain module-level constant so the rest of the
codebase can do ``from config import X`` without carrying a settings
object around. Filesystem roots are ``pathlib.Path`` instances; anything
that plausibly needs to differ between environments (currently just the
CORS origin) can be overridden with an environment variable.
"""

import os
from pathlib import Path

# =========================================================================
# PATHS
# =========================================================================
BASE_DIR: Path = Path(__file__).resolve().parent.parent
EXPORT_PATH: Path = BASE_DIR / "export"
ITEMS_DB_PATH: Path = BASE_DIR / "items.db"
TEMPLATES_DIR: Path = BASE_DIR / "templates"

# =========================================================================
# GENERAL
# =========================================================================
DEBUG: bool = True

# API server CORS. A comma-separated CRAWLVIZ_CORS_ORIGINS overrides the
# Vite dev-server default, e.g. for deploying the frontend elsewhere.
CORS_ORIGINS: list[str] = os.environ.get(
    "CRAWLVIZ_CORS_ORIGINS", "http://localhost:5173"
).split(",")

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
# Identify the crawler honestly: replace the contact before crawling live sites.
USER_AGENT: str = (
    "CrawlViz/1.0 (+https://github.com/omarbounawarapy/crawlviz; "
    "omar.bounawara.py@gmail.com)"
)
RESPECT_ROBOTS: bool = True

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

# Composite NLP score weights (nlp/feature_extractor signals). Fitted with
# tools/nlp_eval.py against LLM labels: target similarity carries the score,
# boilerplate similarity (contact/privacy/... pages) pulls navigation down.
# The other signals stay in `nlp_vector` for the priority strategies.
NLP_COMPOSITE_WEIGHTS: dict[str, float] = {
    "target_similarity": 0.80,
    "contextual_consistency": 0.05,
    "boilerplate_score": -0.35,
}

DEFAULT_PRIORITY_STRATEGY: str = "balanced"

# =========================================================================
# EXPORT
# =========================================================================
EXPORT_BATCH_SIZE: int = 1
