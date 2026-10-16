"""The per-crawl LLM call cap: counting, and what the scoring pipeline does at the cap."""
import logging

import pytest

from infrastructure.call_budget import CallBudget
from pipelines.scoring_pipeline import ScoringPipeline


class L:
    def __init__(self, score, name="x"):
        self._nlp_score = score
        self.name = name


def pipeline(budget, batch=None):
    return ScoringPipeline(
        None, None, None, low_threshold=0.2, high_threshold=0.75,
        high_score_llm_fraction=0.3, low_score_sample_fraction=0.0,
        high_score_random_fraction=0.0, llm_batch_size=batch, call_budget=budget,
    )


def test_no_limit_counts_every_call_and_refuses_none():
    budget = CallBudget(None)
    assert budget.take(5) == 5
    assert budget.take(3) == 3
    assert (budget.used, budget.refused, budget.exhausted) == (8, 0, False)


def test_limit_grants_only_what_is_left_and_counts_the_rest():
    budget = CallBudget(10)
    assert budget.take(7) == 7
    assert budget.take(5) == 3
    assert (budget.used, budget.refused) == (10, 2)
    assert budget.exhausted
    assert budget.take(1) == 0


def test_warns_once_when_the_cap_is_first_reached(caplog):
    budget = CallBudget(1)
    with caplog.at_level(logging.WARNING, logger="infrastructure.call_budget"):
        budget.take(1)
        budget.take(1)
        budget.take(1)
    assert sum("budget of 1 reached" in r.message for r in caplog.records) == 1


def test_snapshot_reports_the_numbers():
    budget = CallBudget(2)
    budget.take(3)
    assert budget.snapshot() == {"limit": 2, "used": 2, "refused": 1, "exhausted": True}


def test_no_budget_leaves_the_bucketing_untouched():
    p = pipeline(None)
    sampled, skip = [L(0.9, "a"), L(0.5, "b")], [L(0.95, "c")]
    assert p._take_llm_calls(sampled, skip) == (sampled, skip)


def test_budget_keeps_the_best_ranked_links_and_trusts_the_rest():
    p = pipeline(CallBudget(1), batch=2)  # one call of two links
    sampled = [L(0.4, "low"), L(0.9, "best"), L(0.6, "mid")]
    kept, moved = p._take_llm_calls(sampled, [L(0.99, "trusted")])
    assert [l.name for l in kept] == ["best", "mid"]
    assert [l.name for l in moved] == ["trusted", "low"]


def test_budget_of_zero_calls_sends_nothing_to_the_llm():
    p = pipeline(CallBudget(0))
    kept, moved = p._take_llm_calls([L(0.5, "a")], [])
    assert kept == []
    assert [l.name for l in moved] == ["a"]


@pytest.mark.parametrize("links,batch,calls", [(5, 2, 3), (4, 2, 2), (1, None, 1)])
def test_a_batched_node_draws_one_call_per_batch(links, batch, calls):
    budget = CallBudget(None)
    p = pipeline(budget, batch=batch)
    p._take_llm_calls([L(0.5, str(i)) for i in range(links)], [])
    assert budget.used == calls
