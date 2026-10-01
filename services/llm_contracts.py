"""Typed shapes for what the scoring and expansion LLM calls return.

Parsing is lenient on values (a score of 500 clamps to 100) but never silent:
each parse reports an outcome so callers can count malformed responses instead
of treating them as ``{}``.
"""
from collections import Counter
from typing import Any

from pydantic import BaseModel, ValidationError, field_validator

VALID_RELEVANCE_TYPES = frozenset({"direct", "partial", "irrelevant", "ambiguous"})


class ScoredLink(BaseModel):
    score: int = 0
    relevance_type: str = "ambiguous"
    expansions: list[str] = []

    @field_validator("score", mode="before")
    @classmethod
    def _score(cls, raw: Any) -> int:
        try:
            return max(0, min(100, int(raw)))
        except (TypeError, ValueError):
            return 0

    @field_validator("relevance_type", mode="before")
    @classmethod
    def _relevance_type(cls, raw: Any) -> str:
        if isinstance(raw, str) and raw.lower() in VALID_RELEVANCE_TYPES:
            return raw.lower()
        return "ambiguous"

    @field_validator("expansions", mode="before")
    @classmethod
    def _expansions(cls, raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        return [s.strip() for s in raw if isinstance(s, str) and s.strip()]


class ExpansionSeeds(BaseModel):
    descriptions: list[str] = []

    @field_validator("descriptions", mode="before")
    @classmethod
    def _descriptions(cls, raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        return [s.strip() for s in raw if isinstance(s, str) and s.strip()]


def parse_scored_link(entry: Any) -> ScoredLink | None:
    """Return the typed entry, or None when it is not an object at all."""
    if not isinstance(entry, dict):
        return None
    try:
        return ScoredLink.model_validate(entry)
    except ValidationError:
        return None


def parse_expansion_seeds(raw: Any) -> ExpansionSeeds | None:
    """Return the typed seeds, or None when the response is not an object."""
    if not isinstance(raw, dict):
        return None
    try:
        return ExpansionSeeds.model_validate(raw)
    except ValidationError:
        return None


class Outcomes(Counter):
    """Counts of how each parsed response turned out, keyed by outcome name."""
