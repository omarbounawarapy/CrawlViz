"""
strategy.py
-----------
Strategy registry for priority computation.

Each strategy is a pure function with the signature:
    priority(node, link, nlp_bias, llm_bias) -> float

Inputs available on every link after the scoring pipeline:
    link._nlp_score          float  0-1   composite NLP score
    link.nlp_vector          dict         all NLP feature signals
    link.score               int    0-100 LLM score (may be None -> 0)

Inputs available on every node:
    node.get_depth()         int          depth in the crawl tree

All weights are explicit. No branching. No LLM calls. No embeddings.

NOT to be confused with the LLM *scoring* strategies in
models/prompts.py (TOPICAL / PATHFINDING / EXPLORATION / GOAL_ORIENTED /
DENSITY_FOCUSED / UNCERTAINTY_BIASED, blueprint key: scoring.strategy),
which bias how the scoring LLM's prompt is worded. This module's three
strategies (blueprint key: stop_conditions.priority_strategy) instead
rank the frontier queue using scores the LLM call already produced --
they never talk to an LLM themselves. Note in particular that this
module's "exploration" and the LLM strategy "EXPLORATION" are different
concepts that happen to share a name.
"""

from collections.abc import Callable
from typing import Any

# =========================================================
# HELPERS
# =========================================================

def _nlp(link, key: str, default: float = 0.0) -> float:
    """Safe accessor for nlp_vector entries."""
    vec = getattr(link, "nlp_vector", None)
    if not vec:
        return default
    return float(vec.get(key, default))


def _llm(link) -> float:
    """LLM score normalized to 0-1. Defaults to 0 if absent."""
    raw = getattr(link, "score", None)
    if raw is None:
        return 0.0
    return max(0.0, min(1.0, float(raw) / 100.0))


def _depth_penalty(node, scale: float) -> float:
    """Linear depth penalty; `scale` controls how aggressive the decay is."""
    return node.get_depth() * scale


# =========================================================
# STRATEGY 1 -- AGGRESSIVE
# Goal: converge on target as fast as possible
# Bias: high relevance + LLM confidence, punish depth hard
# =========================================================

DEFAULT_WEIGHTS: dict[str, dict[str, float]] = {
    "aggressive": {
        "target_similarity": 0.40,
        "coverage_gap": 0.15,
        "novelty_injection": 0.10,
        "contextual_consistency": 0.05,
        "depth_penalty": 0.08,
    },
    "balanced": {
        "target_similarity": 0.25,
        "novelty_injection": 0.20,
        "coverage_gap": 0.15,
        "contextual_consistency": 0.10,
        "lexical_overlap": 0.05,
        "depth_penalty": 0.05,
    },
    "exploration": {
        "novelty_injection": 0.35,
        "cluster_distance": 0.25,
        "coverage_gap": 0.20,
        "target_similarity": 0.05,
        "semantic_delta": 0.05,
        "depth_penalty": 0.03,
    },
}

# Features a strategy may weight (the NLP feature vector keys), plus the
# per-depth penalty. Used to validate user-supplied weights.
WEIGHT_KEYS = frozenset(
    {k for w in DEFAULT_WEIGHTS.values() for k in w}
    | {"region_density", "anchor_similarity", "parent_relevance", "boilerplate_score"}
)


def _score(strategy: str, node, link, nlp_bias, llm_bias, weights) -> float:
    w = weights if weights is not None else DEFAULT_WEIGHTS[strategy]
    nlp = sum(wt * _nlp(link, key) for key, wt in w.items() if key != "depth_penalty")
    nlp -= _depth_penalty(node, w.get("depth_penalty", 0.0))
    return round(max(0.0, nlp_bias * nlp + llm_bias * _llm(link)), 6)


def aggressive(node, link, nlp_bias, llm_bias, weights=None) -> float:
    """Most directly relevant links first; depth is a strong penalty, so
    shallow high-confidence paths win. Weights: DEFAULT_WEIGHTS["aggressive"]."""
    return _score("aggressive", node, link, nlp_bias, llm_bias, weights)


# =========================================================
# STRATEGY 2 -- BALANCED
# Goal: stable, broad crawling without runaway exploration or tunnel vision
# =========================================================

def balanced(node, link, nlp_bias: float = 0.5, llm_bias: float = 0.5, weights=None) -> float:
    return _score("balanced", node, link, nlp_bias, llm_bias, weights)


# =========================================================
# STRATEGY 3 -- EXPLORATION
# Goal: discover semantically distant, under-covered regions
# Bias: novelty + cluster distance + coverage gap; LLM score is a weak signal
# =========================================================

def exploration(node, link, nlp_bias: float = 0.85, llm_bias: float = 0.15, weights=None) -> float:
    return _score("exploration", node, link, nlp_bias, llm_bias, weights)


# =========================================================
# REGISTRY
# =========================================================

StrategyFn = Callable[[Any, Any, float, float], float]

STRATEGY_REGISTRY: dict[str, StrategyFn] = {
    "aggressive": aggressive,
    "balanced": balanced,
    "exploration": exploration,
}


def get_strategy(name: str, weights: dict[str, float] | None = None) -> StrategyFn:
    """Resolve a strategy by name; `weights` replaces its built-in feature
    weights (keys: WEIGHT_KEYS) for the returned function.

    Raises:
        ValueError: If `name` is not a registered strategy.
    """
    fn = STRATEGY_REGISTRY.get(name)
    if fn is None:
        raise ValueError(
            f"Unknown priority strategy: {name!r}. "
            f"Registered strategies: {list(STRATEGY_REGISTRY)}"
        )
    if weights is not None and name in DEFAULT_WEIGHTS:
        return lambda node, link, nlp_bias, llm_bias: fn(
            node, link, nlp_bias, llm_bias, weights=weights
        )
    return fn


def register_strategy(name: str, fn: StrategyFn) -> None:
    """Register a custom strategy at runtime.

    `fn` must satisfy: fn(node, link, nlp_bias, llm_bias) -> float
    """
    STRATEGY_REGISTRY[name] = fn
