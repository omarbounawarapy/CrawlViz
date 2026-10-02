"""The frozen-graph benchmark runs policies through the real pipelines."""
from benchmark import POLICIES, run_policy, synthetic_graph


async def test_every_policy_fills_the_budget_on_a_connected_graph():
    graph = synthetic_graph(n_pages=200, seed=1)
    for name in POLICIES:
        result = await run_policy(graph, name, 40)
        assert len(result.visited) == 40, name
        assert len(set(result.visited)) == 40, name


async def test_same_seed_gives_the_same_visit_order():
    graph = synthetic_graph(n_pages=200, seed=2)
    first = await run_policy(graph, "random", 40, seed=5)
    second = await run_policy(graph, "random", 40, seed=5)
    assert first.visited == second.visited


async def test_oracle_beats_bfs_and_lexical_beats_random():
    # Summed over several graphs: one graph's gap can be inside the noise.
    found = dict.fromkeys(POLICIES, 0)
    for seed in range(4):
        graph = synthetic_graph(n_pages=300, seed=seed)
        for name in POLICIES:
            found[name] += (await run_policy(graph, name, 80)).found(80)
    assert found["oracle"] > found["bfs"]
    assert found["anchor_lexical"] > found["random"]


async def test_recorded_pages_are_served_as_the_markup_extraction_expects():
    from benchmark import FrozenGraph

    graph = FrozenGraph(
        seed="A",
        pages={
            "A": {"relevant": None, "title": "Alpha", "text": "About <alpha>.",
                  "links": [{"to": "B", "anchor": "Beta & co"}]},
            "B": {"relevant": None, "title": "Beta", "text": "More.", "links": []},
        },
    )
    body = await graph.fetcher().emit_request({"url": "https://frozen.test/A"})
    assert 'id="firstHeading">Alpha<' in body
    assert "About &lt;alpha&gt;." in body
    assert 'href="/B">Beta &amp; co<' in body


def test_wiki_name_keeps_only_articles():
    from benchmark.record import wiki_name

    assert wiki_name("/wiki/Tunis#Histoire") == "Tunis"
    assert wiki_name("https://fr.wikipedia.org/wiki/Universit%C3%A9") == "Universit%C3%A9"
    assert wiki_name("/wiki/Fichier:X.png") is None
    assert wiki_name("/wiki/AC/DC") is None
    assert wiki_name("/w/index.php?title=X") is None


async def test_llm_cache_answers_a_repeat_without_calling_the_model(tmp_path):
    from benchmark.llm_cache import CachedLlm
    from models.llm_context import LlmContext

    class Inner:
        calls = 0

        async def send(self, context):
            self.calls += 1
            return {"labels": {"1": True}}

    inner = Inner()
    ctx = lambda: LlmContext("groq", "m", "prompt")
    first = CachedLlm(inner, tmp_path / "c.jsonl")
    await first.send(ctx())
    await first.send(ctx())
    assert (inner.calls, first.hits) == (1, 1)
    assert await CachedLlm(inner, tmp_path / "c.jsonl").send(ctx()) == {"labels": {"1": True}}
    assert inner.calls == 1


async def test_llm_cache_scopes_give_independent_realizations_and_replay_each(tmp_path):
    from benchmark.llm_cache import CachedLlm
    from models.llm_context import LlmContext

    class Inner:
        calls = 0

        async def send(self, context):
            self.calls += 1
            return {"answer": self.calls}  # a different realization every live call

    inner, path = Inner(), tmp_path / "c.jsonl"
    ctx = lambda: LlmContext("groq", "m", "same prompt")
    rep0 = await CachedLlm(inner, path, scope="rep0").send(ctx())
    rep1 = await CachedLlm(inner, path, scope="rep1").send(ctx())
    assert rep0 != rep1 and inner.calls == 2  # repeat 1 did not replay repeat 0
    assert await CachedLlm(inner, path, scope="rep0").send(ctx()) == rep0
    assert await CachedLlm(inner, path, scope="rep1").send(ctx()) == rep1
    assert inner.calls == 2


def test_unscoped_cache_key_is_the_original_one(tmp_path):
    import hashlib

    from benchmark.llm_cache import CachedLlm
    from models.llm_context import LlmContext

    ctx = LlmContext("groq", "m", "p")
    assert CachedLlm(None, tmp_path / "c").key(ctx) == hashlib.sha256(b"groq\0m\0p").hexdigest()
    assert CachedLlm(None, tmp_path / "c", scope="rep0").key(ctx) != CachedLlm(None, tmp_path / "c").key(ctx)


# --- Threats to the validity of a measurement -------------------------------

import pytest


async def test_visit_order_does_not_depend_on_scoring_latency():
    # Lockstep: a page is fetched only after the previous page's scoring has landed.
    import asyncio

    from benchmark import policies, runner

    class Slow(policies.AnchorLexical):
        delay = 0.0

        async def score_links(self, links, parent):
            await asyncio.sleep(Slow.delay)
            return await super().score_links(links, parent)

    graph = synthetic_graph(n_pages=300, seed=1)
    policies.POLICIES["slow"] = Slow
    try:
        orders = []
        for delay in (0.0, 0.03):
            Slow.delay = delay
            orders.append((await runner.run_policy(graph, "slow", 40)).visited)
    finally:
        del policies.POLICIES["slow"]
    assert orders[0] == orders[1]


async def test_space_growth_is_committed_by_count_not_by_clock():
    import asyncio

    from benchmark.runner import _CountedFlush

    class Nlp:
        async def update_space(self, results):
            pass

    class Updater:
        flushes = 0

        async def force_flush(self):
            Updater.flushes += 1

    nlp = _CountedFlush(Nlp(), Updater(), every=3)
    seen = []
    for i in range(7):
        await asyncio.sleep(0.02 if i % 2 else 0)  # timing must not matter
        await nlp.update_space([])
        seen.append(Updater.flushes)
    assert seen == [0, 0, 1, 1, 1, 2, 2]


async def test_a_run_whose_scoring_fails_is_invalid():
    from benchmark import policies, runner

    class Broken(policies.Bfs):
        async def score_links(self, links, parent):
            raise RuntimeError("llm unavailable")

    policies.POLICIES["broken"] = Broken
    try:
        result = await runner.run_policy(synthetic_graph(n_pages=100, seed=1), "broken", 20)
    finally:
        del policies.POLICIES["broken"]
    assert not result.health.valid
    assert result.health.scoring_failures > 0
    assert any("pages" in p or "gave up" in p for p in result.health.problems)


async def test_a_healthy_run_is_valid():
    from benchmark import run_policy

    result = await run_policy(synthetic_graph(n_pages=100, seed=1), "bfs", 20)
    assert result.health.valid, result.health.problems


def test_handled_empty_answers_are_reported_but_do_not_invalidate():
    from benchmark.runner import HealthMonitor, _ErrorLog, assess

    class Retry:
        max_scoring_retries = 3
        _scoring_retry_counts = {"n1": 1}  # retried once, then scored

    monitor = HealthMonitor()
    monitor.empties_seen, monitor.failures_seen = 2, 1
    health = assess(10, list(range(10)), monitor, Retry(), _ErrorLog())
    assert health.valid and health.empty_results == 2 and health.scoring_failures == 1

    Retry._scoring_retry_counts = {"n1": 4}  # gave up: required work never completed
    assert not assess(10, list(range(10)), monitor, Retry(), _ErrorLog()).valid


def test_invalid_repeats_stay_out_of_the_statistics(capsys):
    from benchmark.__main__ import report
    from benchmark.runner import RunHealth, RunResult

    def run(found, problems=()):
        return RunResult("cascade", ["p"] * 10, [True] * found + [False] * (10 - found),
                         RunHealth(problems=list(problems)))

    report("cascade", [run(8), run(6), run(0, ["ended after 3 of 10 pages"])], 10)
    out = capsys.readouterr().out
    assert "7.0" in out and "[8 6]" in out and "2/3 valid" in out and "INVALID" in out


async def test_replay_only_never_calls_the_model_and_fails_loudly(tmp_path):
    from benchmark.llm_cache import CachedLlm, ReplayMiss
    from models.llm_context import LlmContext

    class Inner:
        calls = 0

        async def send(self, context):
            Inner.calls += 1
            return {"x": 1}

    path = tmp_path / "c.jsonl"
    await CachedLlm(Inner(), path, scope="rep0").send(LlmContext("groq", "m", "p"))
    replay = CachedLlm(Inner(), path, scope="rep0", replay_only=True)
    assert await replay.send(LlmContext("groq", "m", "p")) == {"x": 1}
    with pytest.raises(ReplayMiss):
        await replay.send(LlmContext("groq", "m", "other prompt"))
    with pytest.raises(ReplayMiss):  # another repeat's answers are not this repeat's
        await CachedLlm(Inner(), path, scope="rep1", replay_only=True).send(LlmContext("groq", "m", "p"))
    assert Inner.calls == 1 and len(replay.replay_misses) == 1


async def test_visit_order_survives_irregular_scoring_latency():
    import asyncio
    import random

    from benchmark import policies, runner

    class Jittery(policies.AnchorLexical):
        rng = random.Random(0)
        max_delay = 0.0

        async def score_links(self, links, parent):
            await asyncio.sleep(Jittery.rng.random() * Jittery.max_delay)
            return await super().score_links(links, parent)

    graph = synthetic_graph(n_pages=300, seed=2)
    policies.POLICIES["jittery"] = Jittery
    try:
        orders = []
        for max_delay in (0.0, 0.02, 0.05):
            Jittery.max_delay = max_delay
            orders.append((await runner.run_policy(graph, "jittery", 40)).visited)
    finally:
        del policies.POLICIES["jittery"]
    assert orders[0] == orders[1] == orders[2]


def test_an_exhausted_frontier_is_a_valid_early_finish_but_a_stall_is_not():
    from benchmark.runner import HealthMonitor, _ErrorLog, assess

    class Retry:
        max_scoring_retries = 3
        _scoring_retry_counts = {}

    early = assess(100, list(range(40)), HealthMonitor(), Retry(), _ErrorLog(), frontier_empty=True)
    assert early.valid and early.status == "completed_early" and early.reason == "frontier_exhausted"
    stalled = assess(100, list(range(40)), HealthMonitor(), Retry(), _ErrorLog(), frontier_empty=False)
    assert not stalled.valid and stalled.status == "failed"
