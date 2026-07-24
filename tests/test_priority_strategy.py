"""Unit tests for priority/strategy.py.

These are pure functions with no I/O, which makes them the cheapest and
highest-value place to start a test suite -- and, per the engineering
audit, the module where several of this session's earlier bugs actually
lived (the priority_strategy/scoring_strategy naming conflation this
suite guards against by testing each strategy's actual weighting, not
just that it runs).
"""
import pytest

from priority.strategy import (
    STRATEGY_REGISTRY,
    aggressive,
    balanced,
    exploration,
    get_strategy,
    register_strategy,
)


class FakeLink:
    def __init__(self, nlp_vector=None, score=None):
        self.nlp_vector = nlp_vector or {}
        self.score = score


class FakeNode:
    def __init__(self, depth=0):
        self._depth = depth

    def get_depth(self):
        return self._depth


class TestGetStrategy:
    def test_resolves_known_strategies(self):
        for name in ("aggressive", "balanced", "exploration"):
            assert get_strategy(name) is STRATEGY_REGISTRY[name]

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown priority strategy"):
            get_strategy("not_a_real_strategy")

    def test_error_message_lists_registered_strategies(self):
        with pytest.raises(ValueError) as exc_info:
            get_strategy("nope")
        assert "aggressive" in str(exc_info.value)
        assert "balanced" in str(exc_info.value)
        assert "exploration" in str(exc_info.value)


class TestRegisterStrategy:
    def test_registers_and_resolves_custom_strategy(self):
        def custom(node, link, nlp_bias, llm_bias):
            return 42.0

        register_strategy("custom_test_strategy", custom)
        try:
            assert get_strategy("custom_test_strategy") is custom
        finally:
            del STRATEGY_REGISTRY["custom_test_strategy"]


class TestStrategiesShareContract:
    """All three strategies must satisfy the same signature and basic
    output contract, regardless of their internal weighting -- this is
    what lets PriorityPipeline call `self.strategy(node, link, nlp_bias,
    llm_bias)` without caring which one was configured.
    """

    @pytest.mark.parametrize("strategy", [aggressive, balanced, exploration])
    def test_returns_non_negative_float(self, strategy):
        node = FakeNode(depth=0)
        link = FakeLink(nlp_vector={}, score=None)
        result = strategy(node, link, nlp_bias=0.5, llm_bias=0.5)
        assert isinstance(result, float)
        assert result >= 0.0

    @pytest.mark.parametrize("strategy", [aggressive, balanced, exploration])
    def test_never_negative_even_with_heavy_depth_penalty(self, strategy):
        node = FakeNode(depth=1000)
        link = FakeLink(nlp_vector={}, score=None)
        result = strategy(node, link, nlp_bias=1.0, llm_bias=1.0)
        assert result >= 0.0

    @pytest.mark.parametrize("strategy", [aggressive, balanced, exploration])
    def test_missing_nlp_vector_keys_default_to_zero(self, strategy):
        node = FakeNode(depth=0)
        link_empty = FakeLink(nlp_vector={}, score=50)
        link_none = FakeLink(nlp_vector=None, score=50)
        # Should not raise, and should treat missing == explicit 0.0.
        assert strategy(node, link_empty, 0.5, 0.5) == strategy(node, link_none, 0.5, 0.5)

    @pytest.mark.parametrize("strategy", [aggressive, balanced, exploration])
    def test_missing_llm_score_defaults_to_zero(self, strategy):
        node = FakeNode(depth=0)
        link = FakeLink(nlp_vector={"target_similarity": 0.5}, score=None)
        # llm contribution should be exactly 0 when score is None.
        result_with_none = strategy(node, link, nlp_bias=0.0, llm_bias=1.0)
        assert result_with_none == 0.0

    @pytest.mark.parametrize("strategy", [aggressive, balanced, exploration])
    def test_deeper_node_scores_lower_or_equal(self, strategy):
        """Every strategy applies *some* depth penalty -- a deeper node
        with identical link signals should never score higher than a
        shallow one.
        """
        link = FakeLink(nlp_vector={"target_similarity": 0.8, "novelty_injection": 0.8,
                                     "coverage_gap": 0.8, "contextual_consistency": 0.8,
                                     "cluster_distance": 0.8, "semantic_delta": 0.8,
                                     "lexical_overlap": 0.8}, score=80)
        shallow = strategy(FakeNode(depth=0), link, nlp_bias=1.0, llm_bias=1.0)
        deep = strategy(FakeNode(depth=10), link, nlp_bias=1.0, llm_bias=1.0)
        assert deep <= shallow


class TestAggressiveWeighting:
    """Aggressive should weight target_similarity heaviest and punish
    depth harder than balanced/exploration -- this is the actual design
    intent documented in the module, not just "it returns a number".
    """

    def test_target_similarity_dominates(self):
        node = FakeNode(depth=0)
        high_target = FakeLink(nlp_vector={"target_similarity": 1.0}, score=None)
        high_novelty = FakeLink(nlp_vector={"novelty_injection": 1.0}, score=None)
        assert aggressive(node, high_target, 1.0, 0.0) > aggressive(node, high_novelty, 1.0, 0.0)

    def test_depth_penalty_harsher_than_exploration(self):
        link = FakeLink(nlp_vector={"target_similarity": 0.5}, score=None)
        shallow = FakeNode(depth=0)
        deep = FakeNode(depth=5)

        aggressive_drop = aggressive(shallow, link, 1.0, 0.0) - aggressive(deep, link, 1.0, 0.0)
        exploration_drop = exploration(shallow, link, 1.0, 0.0) - exploration(deep, link, 1.0, 0.0)

        assert aggressive_drop > exploration_drop


class TestExplorationWeighting:
    def test_favors_novelty_and_cluster_distance_over_target_similarity(self):
        node = FakeNode(depth=0)
        novel = FakeLink(nlp_vector={"novelty_injection": 1.0, "cluster_distance": 1.0}, score=None)
        on_target = FakeLink(nlp_vector={"target_similarity": 1.0}, score=None)
        assert exploration(node, novel, 1.0, 0.0) > exploration(node, on_target, 1.0, 0.0)

    def test_default_bias_favors_nlp_over_llm(self):
        # exploration's own defaults (nlp_bias=0.85, llm_bias=0.15) should
        # make a strong LLM score matter much less than strong NLP signals.
        node = FakeNode(depth=0)
        strong_llm_only = FakeLink(nlp_vector={}, score=100)
        strong_nlp_only = FakeLink(
            nlp_vector={"novelty_injection": 1.0, "cluster_distance": 1.0}, score=None
        )
        assert exploration(node, strong_nlp_only) > exploration(node, strong_llm_only)


class TestBalancedWeighting:
    def test_uses_five_nlp_signals(self):
        # balanced is documented to spread weight across five signals;
        # confirm each one actually contributes (i.e. isn't dead weight).
        node = FakeNode(depth=0)
        baseline = balanced(node, FakeLink(nlp_vector={}, score=None), 1.0, 0.0)
        for key in (
            "target_similarity", "novelty_injection", "coverage_gap",
            "contextual_consistency", "lexical_overlap",
        ):
            bumped = balanced(node, FakeLink(nlp_vector={key: 1.0}, score=None), 1.0, 0.0)
            assert bumped > baseline, f"{key} did not contribute to balanced's score"
