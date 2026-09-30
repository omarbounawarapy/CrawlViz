"""FeatureExtractor signals and ScoringPipeline bucketing (pure logic, no models)."""
import numpy as np

from nlp.feature_extractor import FeatureExtractor
from pipelines.scoring_pipeline import ScoringPipeline


class L:
    def __init__(self, score):
        self._nlp_score = score


def pipeline(**kw):
    return ScoringPipeline(
        None, None, None, low_threshold=0.2, high_threshold=0.75,
        high_score_llm_fraction=0.3, low_score_sample_fraction=0.0,
        high_score_random_fraction=0.0, **kw,
    )


def test_vocab_coverage_counts_anchor_tokens_in_vocab():
    vocab = {"insulin", "diabetes"}
    assert FeatureExtractor.vocab_coverage("Insulin resistance", vocab) == 0.5
    assert FeatureExtractor.vocab_coverage("", vocab) == 0.0
    assert FeatureExtractor.vocab_coverage("anything", set()) == 0.0


def test_adaptive_radius_is_a_low_percentile_of_pairwise_distance():
    rng = np.random.default_rng(0)
    mat = rng.normal(size=(40, 16))
    r = FeatureExtractor.adaptive_radius(mat, 15)
    norm = mat / np.linalg.norm(mat, axis=1, keepdims=True)
    d = (1 - norm @ norm.T)[np.triu_indices(40, 1)]
    assert abs((d <= r).mean() - 0.15) < 0.02
    assert FeatureExtractor.adaptive_radius(mat[:2]) == 0.3  # too few vectors


def test_boilerplate_score_is_high_for_near_prototype_and_safe_without_any():
    protos = np.array([[1.0, 0.0], [0.0, 1.0]])
    assert FeatureExtractor.boilerplate_score(np.array([0.9, 0.1]), protos) > 0.9
    assert FeatureExtractor.boilerplate_score(np.array([1.0, 1.0]), None) == 0.0


def test_percentile_bucketing_separates_a_narrow_score_band():
    links = [L(0.30 + i * 0.002) for i in range(100)]  # all "mid" under 0.20/0.75
    fixed, _, _ = pipeline().bucket_links(links)
    assert len(fixed) == 100  # fixed thresholds: everything goes to the LLM
    sampled, skipped, dropped = pipeline(
        percentile_bucketing=True, low_percentile=20, high_percentile=75
    ).bucket_links(links)
    assert len(dropped) >= 15 and len(skipped) >= 10 and len(sampled) < 100


def test_max_llm_links_keeps_best_ranked_and_rest_are_not_lost():
    links = [L(i / 100) for i in range(20, 90)]
    sampled, skipped, dropped = pipeline(max_llm_links=10).bucket_links(links)
    assert len(sampled) == 10
    assert len(sampled) + len(skipped) + len(dropped) == len(links)
