"""Central configuration for the CrawlViz backend.

Everything here is a plain module-level constant so the rest of the
codebase can do ``from config import X`` without carrying a settings
object around. Paths are ``pathlib.Path`` instances; anything that
plausibly needs to differ between environments (currently just the
CORS origin) can be overridden with an environment variable.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent.parent
TEMPLATES_DIR: Path = BASE_DIR / "templates"
EXPORT_PATH: Path = BASE_DIR / "export"

# ---------------------------------------------------------------------------
# General
# ---------------------------------------------------------------------------
DEBUG: bool = True

# API server CORS. A comma-separated CRAWLVIZ_CORS_ORIGINS overrides the
# Vite dev-server default, e.g. for deploying the frontend elsewhere.
CORS_ORIGINS: list[str] = os.environ.get(
    "CRAWLVIZ_CORS_ORIGINS", "http://localhost:5173"
).split(",")

# ---------------------------------------------------------------------------
# NLP embeddings
# ---------------------------------------------------------------------------
EMBEDDING_BACKEND: str = "sentence_transformers"
EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
SPACE_STORE_DIR: str = ".space_store"

# How often (and at what buffer size) the semantic space is grown from
# newly-scored links -- see nlp/space_updater.py. Report section 0.12.3
# ("Raffinement iteratif de la base semantique").
FLUSH_INTERVAL_SECONDS: float = 60.0
FLUSH_THRESHOLD: int = 50
BUFFER_MAX_SIZE: int = 500

# ---------------------------------------------------------------------------
# Scoring cascade (report section 0.13 "Evaluation multi-etapes")
# ---------------------------------------------------------------------------
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

DEFAULT_PRIORITY_STRATEGY: str = "balanced"

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
EXPORT_BATCH_SIZE: int = 1
