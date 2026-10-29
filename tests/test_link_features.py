"""LinkFeatureScorer: the parent context and the composite score."""

import asyncio
import warnings
from types import SimpleNamespace

import numpy as np

from nlp import VectorSpace
from nlp.embedding_engine import HashingEmbeddingEngine
from services.link_features import FeatureSettings, LinkFeatureScorer

TOPIC = "insulin resistance and diabetes"


def scorer(weights: dict[str, float] | None = None) -> LinkFeatureScorer:
    return LinkFeatureScorer(HashingEmbeddingEngine(), FeatureSettings(composite_weights=weights))


def test_composite_score_is_the_weighted_sum_clamped_to_one() -> None:
    features = scorer({"a": 1.0, "b": 0.5})
    assert asyncio.run(features.composite_score({"a": 0.2, "b": 0.4})) == 0.4
    assert asyncio.run(features.composite_score({"a": 2.0})) == 1.0
    assert asyncio.run(features.composite_score({"a": -1.0})) == 0.0
    assert asyncio.run(features.composite_score({})) == 0.0


def test_a_parent_without_text_is_scored_as_the_target() -> None:
    engine = HashingEmbeddingEngine()
    space = VectorSpace(dim=engine.dim)
    target = engine.encode(TOPIC)
    space.add_vector(key="__target__bp", vector=target, metadata={"type": "target", "text": TOPIC})
    context = asyncio.run(
        scorer().parent_context(SimpleNamespace(content=""), space, target, TOPIC)
    )
    assert context.content == ""
    assert np.array_equal(context.vector, target)
    assert context.relevance == 1.0
    assert context.cluster_centroids == {}  # too few vectors to cluster


def test_a_parent_with_no_words_is_not_relevant_and_raises_no_warning() -> None:
    engine = HashingEmbeddingEngine()
    space = VectorSpace(dim=engine.dim)
    target = engine.encode(TOPIC)
    space.add_vector(key="__target__bp", vector=target, metadata={"type": "target", "text": TOPIC})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        context = asyncio.run(
            scorer().parent_context(SimpleNamespace(content="<p>!!! ???</p>"), space, target, TOPIC)
        )
    assert not context.vector.any()  # the hashing engine embeds no words as zeros
    assert context.relevance == 0.0
