"""
blueprint_schema.py
--------------------
Pydantic schema for the *assembled* blueprint dict -- the shape every
consumer (core.Crawler, pipelines.exporting_pipeline.ExportingPipeline,
models.item_extractor.ItemExtractor, nlp.SpaceUpdater's caller, ...)
actually reads.

This exists because the informal shape agreement between
BlueprintTranslator (the producer) and its consumers has silently
drifted out of sync three separate times in this codebase's history:

    1. ExportingPipeline read `field_spec["store"]["type"]`, a key that
       never existed anywhere -- the translator only ever produced a
       flat `export_type`. Every field silently exported as TEXT.
    2. `stop_conditions.priority_strategy` was read by core.Crawler but
       never written by BlueprintTranslator at all -- every blueprint
       authored through the UI silently fell back to "balanced" no
       matter what was selected.
    3. The LLM *scoring* strategy (models/prompts.py) and the frontier
       *priority* strategy (priority/strategy.py) share enough surface
       area (both called "strategy" informally, one name "exploration"
       used by both with different meanings) to be conflated in code
       and documentation.

BlueprintTranslator.translate() validates its assembled output against
`Blueprint` as a final pass, on top of (not instead of) its existing
hand-written checks -- so the *next* field anyone adds to a consumer
gets a validation error at blueprint-authoring time instead of a silent
runtime gap, provided this schema is kept in sync too. That's still a
manual step, but a single, declared, importable one instead of five
files' worth of implicit dict-shape agreement.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from config import DEFAULT_PRIORITY_STRATEGY
from priority.strategy import STRATEGY_REGISTRY

# =========================================================
# STRICT ENUMERATIONS -- single source of truth
# =========================================================

# LLM scoring strategy (blueprint key: scoring.strategy) -- biases the
# wording of the prompt sent to the scoring LLM. NOT the same as
# priority_strategy below; see models/prompts.py and priority/strategy.py.
ALLOWED_STRATEGIES: frozenset[str] = frozenset(
    {
        "TOPICAL",
        "PATHFINDING",
        "EXPLORATION",
        "GOAL_ORIENTED",
        "DENSITY_FOCUSED",
        "UNCERTAINTY_BIASED",
    }
)

# Priority strategy (blueprint key: stop_conditions.priority_strategy) --
# sourced directly from the registry so it can't drift out of sync the
# way ALLOWED_STRATEGIES above still has to be hand-maintained (the LLM
# side has no equivalent registry to source from).
ALLOWED_PRIORITY_STRATEGIES: frozenset[str] = frozenset(STRATEGY_REGISTRY)

ALLOWED_EXPORT_TYPES: frozenset[str] = frozenset({"text", "real", "int", "json"})

ALLOWED_FIELD_TYPES: frozenset[str] = frozenset({"scalar", "list"})

_NO_CONFIG_TRANSFORMS: frozenset[str] = frozenset(
    {"strip", "lowercase", "deduplicate", "join"}
)
_PARAMETERISED_TRANSFORMS: dict[str, list[str]] = {
    "truncate": ["max_len"],
    "regex": ["pattern"],
    "regex_extract": ["pattern"],
}
ALLOWED_TRANSFORMS: frozenset[str] = frozenset(
    _NO_CONFIG_TRANSFORMS | set(_PARAMETERISED_TRANSFORMS)
)


class BlueprintSchemaError(ValueError):
    """Raised when an assembled blueprint doesn't match the shape its
    consumers actually expect. BlueprintTranslator catches this and
    re-raises as BlueprintValidationError so callers see one consistent
    exception type regardless of which validation layer caught the
    problem.
    """


# =========================================================
# FIELD-LEVEL SHAPE
# =========================================================
# This is the exact shape models.item_extractor.FieldExtractor and
# pipelines.exporting_pipeline.ExportingPipeline both read -- issue #1
# above was this shape drifting between the translator and
# ExportingPipeline specifically.

class TransformStep(BaseModel):
    model_config = ConfigDict(extra="allow")  # regex/truncate carry extra params

    type: str

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        if v not in ALLOWED_TRANSFORMS:
            raise ValueError(
                f"Unknown transform {v!r}. Allowed: {sorted(ALLOWED_TRANSFORMS)}"
            )
        return v


class FieldSpec(BaseModel):
    selector: str | None = None
    type: Literal["scalar", "list"] = "list"
    transform: list[TransformStep] = Field(default_factory=list)
    export_type: Literal["text", "real", "int", "json"] = "text"


class ExtractionConfig(BaseModel):
    mode: Literal["document", "container"] = "document"
    container: str | None = None
    fields: dict[str, FieldSpec] = Field(default_factory=dict)


# =========================================================
# TOP-LEVEL SECTIONS
# =========================================================

class ScoringParams(BaseModel):
    model_config = ConfigDict(extra="allow")

    scoring_type: str
    model_information: str


class ScoringConfig(BaseModel):
    strategy: str
    params: ScoringParams

    @field_validator("strategy")
    @classmethod
    def _validate_strategy(cls, v: str) -> str:
        if v not in ALLOWED_STRATEGIES:
            raise ValueError(
                f"Unknown strategy {v!r}. Allowed: {sorted(ALLOWED_STRATEGIES)}"
            )
        return v


class ExpansionConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    style: str
    num_descriptions: int
    llm_type: str
    llm_model: str


class Seed(BaseModel):
    model_config = ConfigDict(extra="allow")

    url: str
    domain: str


class DomainConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    base_url: str
    link_selector: str


class StopConditions(BaseModel):
    max_nodes: int
    max_depth: int
    max_duration: float
    no_progress_timeout: float
    stop_url: str = ""
    # This default, and the validator below, are exactly what issue #2
    # in the module docstring was missing until this session.
    priority_strategy: str = Field(default_factory=lambda: DEFAULT_PRIORITY_STRATEGY)

    @field_validator("priority_strategy")
    @classmethod
    def _validate_priority_strategy(cls, v: str) -> str:
        if v not in ALLOWED_PRIORITY_STRATEGIES:
            raise ValueError(
                f"Unknown priority_strategy {v!r}. "
                f"Allowed: {sorted(ALLOWED_PRIORITY_STRATEGIES)}"
            )
        return v


class Blueprint(BaseModel):
    """The full assembled blueprint -- what BootStrapper/Crawler consume.

    `extra="allow"` everywhere except the parts that have already caused
    a real bug (FieldSpec/export_type, StopConditions.priority_strategy,
    ScoringConfig.strategy) -- tightening the rest further is worth doing
    incrementally, as each section proves what its consumers actually
    require, rather than guessing all of it up front.
    """
    model_config = ConfigDict(extra="allow")

    blueprint_id: str
    id: str
    target_topic: str
    seeds: list[Seed]
    domains: dict[str, DomainConfig]
    scoring: ScoringConfig
    expansion: ExpansionConfig
    extraction: ExtractionConfig
    stop_conditions: StopConditions
