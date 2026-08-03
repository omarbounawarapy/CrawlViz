"""
RuntimeConfig
=============
A validated, introspectable schema over the constants in config.py's
"SCORING CASCADE" / "NLP EMBEDDINGS" / "EXPORT" sections -- the tunable
surface a researcher needs visibility into to answer "what assumptions is
this crawl operating under?" (see docs/V2_ARCHITECTURE.md §B.2.3).

Why this exists
----------------
`routes/blueprint_schema.py` already solved this exact problem for
blueprints: a Pydantic model as the single source of truth, with its
JSON schema exported for the frontend rather than hand-duplicated. That
model's own docstring documents three past incidents of drift between
independently-maintained copies of the same shape. `routes/blueprint_ui_schema.json`
took a further step -- a hand-written ui-hints JSON schema for
form-rendering -- but was never wired to anything on either side (dead
file; see docs/V2_ARCHITECTURE.md §A.1.5). This module applies the
working half of that pattern (a Pydantic model, `Field(...)` for both
validation AND ui hints, `.model_json_schema()` generated rather than
hand-copied) to the runtime tuning surface described in the engineering
philosophy brief.

Scope of this pass (see docs/V2_ARCHITECTURE.md roadmap #12 vs #18)
----------------------------------------------------------------------
This model is a validated MIRROR of config.py's current constants,
exposed read-only via `GET /config/schema` and `GET /config`. It does
NOT (yet) become the thing scoring_pipeline.py / priority_pipeline.py
actually read their thresholds from -- doing that safely means touching
every call site that currently does `from config import X`, which is a
larger, separable change from "make the surface introspectable and
validated" and is called out explicitly in the roadmap as follow-up
work, not silently skipped.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

import config as _config


class ScoringCascadeConfig(BaseModel):
    """The two-stage NLP -> LLM relevance cascade's tunable thresholds and
    sampling fractions (report section 0.13, "Evaluation multi-etapes")."""

    low_threshold: float = Field(
        default=_config.NLP_LOW_SCORE_THRESHOLD, ge=0.0, le=1.0,
        description="NLP similarity score below which a link is considered low-confidence.",
        json_schema_extra={"ui_section": "Scoring cascade", "ui_widget": "slider"},
    )
    high_threshold: float = Field(
        default=_config.NLP_HIGH_SCORE_THRESHOLD, ge=0.0, le=1.0,
        description="NLP similarity score above which a link is considered high-confidence.",
        json_schema_extra={"ui_section": "Scoring cascade", "ui_widget": "slider"},
    )
    high_score_llm_fraction: float = Field(
        default=_config.HIGH_SCORE_LLM_FRACTION, ge=0.0, le=1.0,
        description=(
            "Fraction of the high-confidence bucket still sent to the LLM rather than "
            "trusted outright -- this is the cascade's cost-saving lever."
        ),
        json_schema_extra={"ui_section": "Scoring cascade", "ui_widget": "slider"},
    )
    high_score_random_fraction: float = Field(
        default=_config.HIGH_SCORE_RANDOM_FRACTION, ge=0.0, le=1.0,
        description="Of the LLM-bound slice of the high bucket, the fraction chosen at random rather than by top NLP rank (bias correction).",
        json_schema_extra={"ui_section": "Scoring cascade", "ui_widget": "slider"},
    )
    low_score_sample_fraction: float = Field(
        default=_config.LOW_SCORE_SAMPLE_FRACTION, ge=0.0, le=1.0,
        description="Fraction of the low-confidence bucket kept anyway, for exploration, instead of dropped outright.",
        json_schema_extra={"ui_section": "Scoring cascade", "ui_widget": "slider"},
    )
    default_priority_strategy: str = Field(
        default=_config.DEFAULT_PRIORITY_STRATEGY,
        description="Priority strategy used when a blueprint doesn't specify one.",
        json_schema_extra={"ui_section": "Scoring cascade", "ui_widget": "select",
                            "ui_options": ["aggressive", "balanced", "exploration"]},
    )

    @model_validator(mode="after")
    def _thresholds_ordered(self) -> "ScoringCascadeConfig":
        if self.low_threshold >= self.high_threshold:
            raise ValueError(
                f"low_threshold ({self.low_threshold}) must be less than "
                f"high_threshold ({self.high_threshold})"
            )
        return self


class EmbeddingConfig(BaseModel):
    """Semantic-space embedding backend (nlp/vector_space.py, nlp/space_updater.py)."""

    backend: str = Field(
        default=_config.EMBEDDING_BACKEND,
        description="Embedding backend used to build the crawl's semantic space.",
        json_schema_extra={"ui_section": "Embeddings", "ui_widget": "select",
                            "ui_options": ["sentence_transformers"]},
    )
    model_name: str = Field(
        default=_config.EMBEDDING_MODEL,
        description="Model identifier passed to the embedding backend.",
        json_schema_extra={"ui_section": "Embeddings", "ui_widget": "text"},
    )
    flush_interval_seconds: float = Field(
        default=_config.FLUSH_INTERVAL_SECONDS, gt=0,
        description="Maximum time between semantic-space growth flushes.",
        json_schema_extra={"ui_section": "Embeddings", "ui_widget": "number"},
    )
    flush_threshold: int = Field(
        default=_config.FLUSH_THRESHOLD, gt=0,
        description="Buffered scored-link count that triggers an early flush.",
        json_schema_extra={"ui_section": "Embeddings", "ui_widget": "number"},
    )
    buffer_max_size: int = Field(
        default=_config.BUFFER_MAX_SIZE, gt=0,
        description="Upper bound on the flush buffer before backpressure applies.",
        json_schema_extra={"ui_section": "Embeddings", "ui_widget": "number"},
    )


class ExportConfig(BaseModel):
    """Item export / persistence batching (pipelines/exporting_pipeline.py)."""

    batch_size: int = Field(
        default=_config.EXPORT_BATCH_SIZE, gt=0,
        description="Number of transformed items grouped into one export batch.",
        json_schema_extra={"ui_section": "Export", "ui_widget": "number"},
    )


class RuntimeConfig(BaseModel):
    """Top-level runtime configuration: everything a researcher would want
    to see before trusting a crawl's results, beyond the per-run blueprint
    (target topic, seeds, extraction schema) already covered by
    routes/blueprint_schema.py."""

    scoring_cascade: ScoringCascadeConfig = Field(default_factory=ScoringCascadeConfig)
    embeddings: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)


def default_runtime_config() -> RuntimeConfig:
    """The config currently in effect, read from config.py's constants."""
    return RuntimeConfig()
