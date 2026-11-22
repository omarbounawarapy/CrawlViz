"""Default weights of the composite NLP score, one per feature-extractor signal."""

# Fitted with tools/nlp_eval.py against LLM labels: target similarity carries the score,
# boilerplate similarity (contact/privacy/... pages) pulls navigation down. The other
# signals stay in `nlp_vector` for the priority strategies.
_DEFAULT_COMPOSITE_WEIGHTS: dict[str, float] = {
    "target_similarity": 0.80,
    "contextual_consistency": 0.05,
    "boilerplate_score": -0.35,
}


def default_composite_weights() -> dict[str, float]:
    """A fresh copy, so callers can adjust theirs."""
    return dict(_DEFAULT_COMPOSITE_WEIGHTS)
