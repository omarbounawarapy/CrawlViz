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

def aggressive(node, link, nlp_bias, llm_bias) -> float:
    """Prioritizes links that are most directly relevant to the target topic.

    Treats depth as a strong penalty -- prefers shallow, high-confidence paths.

    Weight breakdown:
        target_similarity   0.40   primary signal
        llm_score            llm_bias   LLM confidence
        coverage_gap         0.15   fills holes toward target
        novelty_injection    0.10   small exploration bonus
        contextual_cons.     0.05   anchor context coherence
        depth_penalty       -0.08 * depth
    """
    nlp = (
        0.40 * _nlp(link, "target_similarity")
        + 0.15 * _nlp(link, "coverage_gap")
        + 0.10 * _nlp(link, "novelty_injection")
        + 0.05 * _nlp(link, "contextual_consistency")
        - _depth_penalty(node, 0.08)
    )

    score = llm_bias * _llm(link) + nlp_bias * nlp

    return round(max(0.0, score), 6)


# =========================================================
# STRATEGY 2 -- BALANCED
# Goal: stable, broad crawling without runaway exploration or tunnel vision
# Bias: equal weight across relevance, novelty, LLM and depth
# =========================================================

def balanced(node, link, nlp_bias: float = 0.5, llm_bias: float = 0.5) -> float:
    nlp = (
        0.25 * _nlp(link, "target_similarity")
        + 0.20 * _nlp(link, "novelty_injection")
        + 0.15 * _nlp(link, "coverage_gap")
        + 0.10 * _nlp(link, "contextual_consistency")
        + 0.05 * _nlp(link, "lexical_overlap")
        - _depth_penalty(node, 0.05)
    )

    return round(max(0.0, nlp_bias * nlp + llm_bias * _llm(link)), 6)


# =========================================================
# STRATEGY 3 -- EXPLORATION
# Goal: discover semantically distant, under-covered regions
# Bias: novelty + cluster distance + coverage gap; LLM score is a weak signal
# =========================================================

def exploration(node, link, nlp_bias: float = 0.85, llm_bias: float = 0.15) -> float:
    nlp = (
        0.35 * _nlp(link, "novelty_injection")
        + 0.25 * _nlp(link, "cluster_distance")
        + 0.20 * _nlp(link, "coverage_gap")
        + 0.05 * _nlp(link, "target_similarity")
        + 0.05 * _nlp(link, "semantic_delta")
        - _depth_penalty(node, 0.03)
    )

    return round(max(0.0, nlp_bias * nlp + llm_bias * _llm(link)), 6)


# =========================================================
# REGISTRY
# =========================================================

StrategyFn = Callable[[Any, Any, float, float], float]

STRATEGY_REGISTRY: dict[str, StrategyFn] = {
    "aggressive": aggressive,
    "balanced": balanced,
    "exploration": exploration,
}


def get_strategy(name: str) -> StrategyFn:
    """Resolve a strategy by name.

    Raises:
        ValueError: If `name` is not a registered strategy.
    """
    fn = STRATEGY_REGISTRY.get(name)
    if fn is None:
        raise ValueError(
            f"Unknown priority strategy: {name!r}. "
            f"Registered strategies: {list(STRATEGY_REGISTRY)}"
        )
    return fn


def register_strategy(name: str, fn: StrategyFn) -> None:
    """Register a custom strategy at runtime.

    `fn` must satisfy: fn(node, link, nlp_bias, llm_bias) -> float
    """
    STRATEGY_REGISTRY[name] = fn
