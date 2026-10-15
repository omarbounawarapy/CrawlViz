"""The frozen-graph benchmark runs policies through the real pipelines."""
import pytest

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
    def ctx():
        return LlmContext("groq", "m", "prompt")

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
    def ctx():
        return LlmContext("groq", "m", "same prompt")

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


async def test_graph_names_are_encoded_the_way_the_crawler_asks_for_them():
    from benchmark import FrozenGraph

    graph = FrozenGraph(
        seed="Université",
        pages={
            "Université": {"relevant": False, "title": "U", "text": "t",
                           "links": [{"to": "Économie_(discipline)", "anchor": "eco"}]},
            "Économie_(discipline)": {"relevant": False, "title": "E", "text": "t", "links": []},
        },
    )
    assert graph.seed == "Universit%C3%A9"
    assert set(graph.pages) == {"Universit%C3%A9", "%C3%89conomie_(discipline)"}
    assert graph.pages["Universit%C3%A9"]["links"][0]["to"] == "%C3%89conomie_(discipline)"
    body = await graph.fetcher().emit_request({"url": "https://frozen.test/%C3%89conomie_(discipline)"})
    assert "E" in body


def test_duplicate_titles_are_reported_and_can_be_merged():
    from benchmark import FrozenGraph

    def page(title, *targets):
        return {"relevant": False, "title": title, "text": "t",
                "links": [{"to": t, "anchor": t} for t in targets]}

    graph = FrozenGraph(
        seed="A",
        pages={"A": page("A", "B", "C"), "B": page("Beta", "D"), "C": page("Beta", "E"),
               "D": page("D"), "E": page("E")},
    )
    assert graph.duplicate_titles() == {"Beta": ["B", "C"]}
    graph.merge("B", "C")
    assert "C" not in graph.pages
    assert [l["to"] for l in graph.pages["A"]["links"]] == ["B"]
    assert {l["to"] for l in graph.pages["B"]["links"]} == {"D", "E"}
    assert not graph.duplicate_titles()


def test_loading_a_graph_with_duplicate_titles_warns(tmp_path):
    from benchmark import FrozenGraph

    page = {"relevant": False, "title": "Same", "text": "t", "links": []}
    path = tmp_path / "g.json"
    FrozenGraph(seed="A", pages={"A": dict(page), "B": dict(page)}).save(path)
    with pytest.warns(UserWarning, match="shared by several pages"):
        FrozenGraph.load(path)


def test_graded_labels_fall_back_to_relevant_and_tolerate_missing_fields():
    from benchmark import FrozenGraph

    graph = FrozenGraph(
        seed="A",
        pages={
            "A": {"label": 2, "links": []},
            "B": {"label": 1, "links": []},
            "C": {"relevant": True, "links": []},
            "D": {"relevant": False, "links": []},
            "E": {"relevant": None, "label": None, "links": []},
        },
    )
    assert [graph.label(n) for n in "ABCDE"] == [2, 1, 1, 0, 0]
    assert graph.relevant() == {"A", "B", "C"}


def test_found_counts_neighbourhood_and_direct_targets_separately():
    from benchmark.runner import RunResult

    result = RunResult("x", list("abcde"), [0, 1, 2, 0, 2])
    assert (result.found(5), result.found_direct(5)) == (3, 2)
    assert (result.found(3), result.found_direct(3)) == (2, 1)
    assert result.harvest(4) == 0.5


async def test_oracle_ranks_direct_targets_before_the_neighbourhood():
    from benchmark import FrozenGraph

    def page(label, *targets):
        return {"label": label, "title": "t", "text": "t",
                "links": [{"to": t, "anchor": t} for t in targets]}

    graph = FrozenGraph(
        seed="S",
        pages={"S": page(0, "N", "Z", "D"), "N": page(1), "Z": page(0), "D": page(2)},
    )
    result = await run_policy(graph, "oracle", 4)
    assert result.visited[:3] == ["S", "D", "N"]
    assert result.labels[:3] == [0, 2, 1]


async def test_llm_cache_counts_tokens_for_live_and_replayed_answers(tmp_path):
    from benchmark.llm_cache import CachedLlm
    from models.llm_context import LlmContext

    class Inner:
        async def send(self, context):
            context.set_usage(100, 20)
            return {"labels": {"1": True}}

    def ctx():
        return LlmContext("groq", "m", "prompt")

    live = CachedLlm(Inner(), tmp_path / "c.jsonl")
    await live.send(ctx())
    await live.send(ctx())  # served from the cache, still costs what it cost
    assert (live.input_tokens, live.output_tokens) == (200, 40)
    replay = CachedLlm(Inner(), tmp_path / "c.jsonl", replay_only=True)
    await replay.send(ctx())
    assert (replay.input_tokens, replay.output_tokens) == (100, 20)


async def test_every_run_leaves_a_result_file_and_a_sequence_entry(tmp_path):
    from benchmark.results import ResultSink, RunRecord, load_records

    graph = synthetic_graph(n_pages=120, seed=3)
    sink = ResultSink(tmp_path / "results", tmp_path / "seq.json")
    for name in ("bfs", "oracle"):
        for rep in range(2):
            result = await run_policy(graph, name, 20, seed=rep)
            sink.add(RunRecord.from_result("g.json", rep, 20, result, llm_calls=3, input_tokens=9))
    records = load_records(tmp_path / "results")
    assert len(records) == 4
    first = next(r for r in records if r.policy == "oracle" and r.rep == 1)
    assert len(first.sequence) == 20 and first.valid and first.llm_calls == 3 and first.input_tokens == 9
    import json

    saved = json.loads((tmp_path / "seq.json").read_text())
    assert set(saved) == {f"g.json:{p}:rep{r}" for p in ("bfs", "oracle") for r in (0, 1)}
    assert saved["g.json:oracle:rep1"] == first.sequence


def _record(policy, rep, labels, valid=True):
    from benchmark.results import RunRecord

    return RunRecord(graph="g", policy=policy, rep=rep, budget=len(labels), sequence=["p"] * len(labels),
                     labels=labels, valid=valid, status="completed" if valid else "failed")


def test_analysis_excludes_invalid_runs_and_pairs_the_wilcoxon_test():
    from benchmark.analyze import by_policy, harvest_at, mean_ci, wilcoxon

    records = [_record("cascade", r, [1] * (6 + r) + [0] * (4 - r)) for r in range(8)]
    records += [_record("bfs", r, [1] * 3 + [0] * 7) for r in range(8)]
    records += [_record("bfs", 9, [1] * 10, valid=False)]
    groups = by_policy(records)
    assert len(groups["bfs"]) == 8
    assert harvest_at([1, 0, 2, 0], 4) == 0.5
    mean, ci = mean_ci([0.5, 0.7, 0.9])
    assert mean == pytest.approx(0.7) and ci > 0
    (row,) = wilcoxon(groups, 10)
    assert row["n"] == 8 and row["p"] < 0.05 and row["subject_mean"] > row["other_mean"]


def test_identical_policies_give_p_of_one_instead_of_crashing():
    from benchmark.analyze import by_policy, wilcoxon

    records = [_record(p, r, [1, 0, 1, 0]) for p in ("cascade", "bfs") for r in range(3)]
    (row,) = wilcoxon(by_policy(records), 4)
    assert row["p"] == 1.0


def test_latex_tables_name_every_policy():
    from benchmark.analyze import by_policy, harvest_table_tex, wilcoxon, wilcoxon_table_tex

    records = [_record(p, r, [1, 0] * 5) for p in ("cascade", "anchor_lexical") for r in range(3)]
    groups = by_policy(records)
    table = harvest_table_tex(groups, ks=(5, 10))
    assert r"anchor\_lexical" in table and r"\toprule" in table and "0.600" in table
    assert r"anchor\_lexical" in wilcoxon_table_tex(wilcoxon(groups, 10), 10)


async def test_waiting_on_a_rate_limit_does_not_count_as_a_stall():
    import asyncio

    from benchmark import runner
    from benchmark.policies import AnchorLexical

    state = {"waiting": False, "slept": False}

    class RateLimited(AnchorLexical):
        async def score_links(self, links, parent):
            if not state["slept"]:  # one back-off longer than the 0.5s idle limit
                state["slept"] = state["waiting"] = True
                await asyncio.sleep(0.9)
                state["waiting"] = False
            return await super().score_links(links, parent)

    kwargs = dict(low_threshold=-1.0, high_threshold=2.0, high_score_llm_fraction=0.0,
                  low_score_sample_fraction=0.0, high_score_random_fraction=0.0,
                  percentile_bucketing=False, max_llm_links=None)
    graph = synthetic_graph(n_pages=100, seed=1)

    def run(**extra):
        state.update(waiting=False, slept=False)
        return runner._run(graph, "x", 15, 0, (runner._NoLlm(), RateLimited(graph, 0)), kwargs,
                           runner._passthrough, [], **extra)

    stalled = await run()
    assert len(stalled.visited) < 15  # without the signal the same wait ends the run
    paused = await run(rate_limited=lambda: state["waiting"])
    assert paused.health.valid and len(paused.visited) == 15
    assert paused.rate_limit_seconds >= 0.8


async def test_paced_llm_reports_waiting_while_it_backs_off(monkeypatch):
    import asyncio

    import aiohttp

    from benchmark.llm_cache import CachedLlm, PacedLlm
    from models.llm_context import LlmContext

    class Limited:
        client = None
        calls = 0

        async def send(self, context):
            self.calls += 1
            if self.calls == 1:
                raise aiohttp.ClientResponseError(None, (), status=429)
            return {"ok": True}

    seen = []
    real_sleep = asyncio.sleep

    async def fake_sleep(seconds):
        seen.append((paced.waiting, cached.waiting, seconds))
        await real_sleep(0)

    paced = PacedLlm(Limited())
    cached = CachedLlm(paced, "unused.jsonl")
    monkeypatch.setattr("benchmark.llm_cache.asyncio.sleep", fake_sleep)
    await paced.send(LlmContext("groq", "m", "p"))
    assert seen == [(True, True, 15)]
    assert not paced.waiting and paced.rate_limit_seconds == 15 and paced.rate_limit_waits == 1


async def test_a_replay_makes_exactly_the_calls_the_live_run_made(tmp_path, monkeypatch):
    # Live run with a jittery fake LLM, then a replay-only run on the same
    # cache: same pages, same calls, nothing unrecorded. The last page's
    # scoring used to race the stop, so the replay asked for one extra answer.
    import asyncio
    import json
    import random
    import re
    import zlib
    from pathlib import Path

    import config.runtime_config as rc
    from benchmark.llm_cache import CachedLlm
    from benchmark.runner import run_cascade

    real = rc.default_runtime_config

    def hashing_config():
        cfg = real()
        cfg.embeddings.backend = "hashing"
        cfg.scoring_cascade.low_threshold, cfg.scoring_cascade.high_threshold = -1.0, 0.9
        return cfg

    monkeypatch.setattr(rc, "default_runtime_config", hashing_config)

    class FakeLlm:
        rng = random.Random(7)

        async def send(self, ctx):
            await asyncio.sleep(self.rng.random() * 0.03)
            prompt = ctx.get_prompt()
            match = re.search(r"CANDIDATES:\n(\[.*?\])\n", prompt, re.S)
            if not match:
                return {"target": "t", "descriptions": ["diabetes insulin glucose", "pancreas care"]}
            urls = [c["url"] for c in json.loads(match.group(1))]
            return {"results": [
                {"url": u, "score": zlib.crc32(u.encode()) % 100, "relevance_type": "direct",
                 "expansions": [f"insulin {u}"] if zlib.crc32(u.encode()) % 5 == 0 else []}
                for u in urls
            ]}

    graph = synthetic_graph(n_pages=200, seed=4)
    graph.topic = "diabetes insulin"
    bp = json.loads(Path("templates/isi.json").read_text())
    expansion = {**bp["expansion"], "llm_type": "groq", "llm_model": "m"}

    async def run(replay_only):
        llm = CachedLlm(FakeLlm(), tmp_path / "c.jsonl", scope="rep0", replay_only=replay_only)
        result = await run_cascade(graph, 25, 0, llm, bp["extraction"], expansion,
                                   bp["scoring"]["strategy"], ("groq", "m"),
                                   tmp_path / f"store-{replay_only}")
        return result, llm

    live, live_llm = await run(False)
    replay, replay_llm = await run(True)
    assert live.health.valid and len(live.visited) == 25
    assert replay.visited == live.visited
    assert not replay_llm.replay_misses
    assert replay_llm.hits == live_llm.misses


def _hashing_config(monkeypatch):
    import config.runtime_config as rc

    real = rc.default_runtime_config

    def patched():
        cfg = real()
        cfg.embeddings.backend = "hashing"
        cfg.scoring_cascade.low_threshold, cfg.scoring_cascade.high_threshold = 0.0, 1.0
        return cfg

    monkeypatch.setattr(rc, "default_runtime_config", patched)


class _RecordingLlm:
    """Answers expansion and scoring prompts; remembers how many links each scoring call carried."""

    def __init__(self):
        self.batches: list[int] = []

    async def send(self, ctx):
        import json
        import re

        match = re.search(r"CANDIDATES:\n(\[.*?\])\n", ctx.get_prompt(), re.S)
        if not match:
            return {"target": "t", "descriptions": ["diabetes insulin glucose", "pancreas care"]}
        urls = [c["url"] for c in json.loads(match.group(1))]
        self.batches.append(len(urls))
        return {"results": [{"url": u, "score": 50, "relevance_type": "direct", "expansions": []} for u in urls]}


def _fan_out_graph(links: int = 130):
    leaves = {f"L{i}": {"label": 0, "title": f"L{i}", "text": "t", "links": []} for i in range(links)}
    seed = {"label": 0, "title": "S", "text": "t",
            "links": [{"to": f"L{i}", "anchor": f"leaf {i}"} for i in range(links)]}
    from benchmark import FrozenGraph

    return FrozenGraph(seed="S", pages={"S": seed, **leaves}, topic="diabetes insulin")


async def _arm(tmp_path, arm, llm, **kw):
    import json
    from pathlib import Path

    from benchmark.llm_cache import CachedLlm
    from benchmark.runner import run_cascade

    bp = json.loads(Path("templates/isi.json").read_text())
    expansion = {**bp["expansion"], "llm_type": "groq", "llm_model": "m"}
    cached = llm if isinstance(llm, CachedLlm) else CachedLlm(llm, tmp_path / f"{arm}.jsonl", scope="rep0")
    result = await run_cascade(_fan_out_graph(), 4, 0, cached, bp["extraction"], expansion,
                               bp["scoring"]["strategy"], ("groq", "m"), tmp_path / f"s-{arm}-{id(cached)}", arm=arm, **kw)
    return result, cached


async def test_llm_all_sends_every_link_in_calls_of_the_cascades_size(tmp_path, monkeypatch):
    from config import MAX_LLM_LINKS_PER_NODE

    _hashing_config(monkeypatch)
    cascade_llm, all_llm = _RecordingLlm(), _RecordingLlm()
    await _arm(tmp_path, "cascade", cascade_llm)
    result, _ = await _arm(tmp_path, "llm_all", all_llm)
    assert cascade_llm.batches[0] == MAX_LLM_LINKS_PER_NODE  # the cascade truncates the node's 130 links
    first_node = all_llm.batches[:3]
    assert first_node == [MAX_LLM_LINKS_PER_NODE, MAX_LLM_LINKS_PER_NODE, 130 - 2 * MAX_LLM_LINKS_PER_NODE]
    assert result.policy == "llm_all" and result.health.valid
    assert result.thresholds["mode"] == "none"
    plain, _ = await _arm(tmp_path, "cascade", _RecordingLlm())
    assert plain.thresholds["mode"] == "percentile"
    assert (plain.thresholds["low_percentile"], plain.thresholds["high_percentile"]) == (20, 75)
    pct, _ = await _arm(tmp_path, "cascade", _RecordingLlm(), low_pct=30, high_pct=80)
    assert pct.thresholds["low_percentile"] == 30
    absolute, _ = await _arm(tmp_path, "cascade", _RecordingLlm(), low=0.3, high=0.6)
    assert absolute.thresholds["mode"] == "absolute" and absolute.thresholds["low"] == 0.3


async def test_no_llm_makes_no_scoring_call_and_reuses_the_recorded_expansion(tmp_path, monkeypatch):
    from benchmark.llm_cache import CachedLlm, ReplayMiss

    _hashing_config(monkeypatch)
    recorder = _RecordingLlm()
    await _arm(tmp_path, "cascade", recorder)  # records the expansion under scope rep0
    replay = CachedLlm(None, tmp_path / "cascade.jsonl", scope="rep0", replay_only=True)
    result, _ = await _arm(tmp_path, "no_llm", replay)
    assert result.policy == "no_llm" and result.health.valid
    assert replay.hits == 1 and not replay.replay_misses  # the expansion, nothing else
    empty = CachedLlm(None, tmp_path / "empty.jsonl", scope="rep0", replay_only=True)
    await _arm(tmp_path, "no_llm", empty)
    assert empty.replay_misses  # an unrecorded expansion is visible, not silently an empty topic


async def test_bad_arm_or_thresholds_are_rejected(tmp_path, monkeypatch):
    _hashing_config(monkeypatch)
    with pytest.raises(ValueError, match="unknown arm"):
        await _arm(tmp_path, "nope", _RecordingLlm())
    with pytest.raises(ValueError, match="below"):
        await _arm(tmp_path, "cascade", _RecordingLlm(), low=0.8, high=0.3)
    with pytest.raises(ValueError, match="only apply"):
        await _arm(tmp_path, "llm_all", _RecordingLlm(), low=0.1)


def test_analysis_counts_each_title_once(tmp_path):
    import json

    from benchmark.analyze import dedupe_records

    graph = {"seed": "A", "pages": {
        "A": {"title": "Alpha", "links": []}, "A2": {"title": "Alpha", "links": []},
        "B": {"title": "Beta", "links": []}}}
    (tmp_path / "g.json").write_text(json.dumps(graph))
    run = _record("bfs", 0, [1, 1, 0])
    run.sequence = ["A", "A2", "B"]
    run.graph = "g.json"
    other = _record("bfs", 1, [1])
    other.graph = "synthetic0"  # no graph file: left as is
    first, second = dedupe_records([run, other], tmp_path)
    assert first.sequence == ["A", "B"] and first.labels == [1, 0]
    assert second.labels == [1]


async def test_percentile_overrides_are_validated_and_exclusive(tmp_path, monkeypatch):
    _hashing_config(monkeypatch)
    with pytest.raises(ValueError, match="below high_pct"):
        await _arm(tmp_path, "cascade", _RecordingLlm(), low_pct=80, high_pct=20)
    with pytest.raises(ValueError, match="different bucketing modes"):
        await _arm(tmp_path, "cascade", _RecordingLlm(), low=0.1, low_pct=10)
    result, _ = await _arm(tmp_path, "cascade", _RecordingLlm(), low_pct=10, high_pct=90)
    assert result.health.valid


async def test_quiet_queue_chooses_among_all_arrivals_once_the_crawler_is_quiet():
    import asyncio
    from types import SimpleNamespace

    from benchmark.runner import _QuietQueue

    queue, quiet = _QuietQueue(), {"now": False}
    queue.gate = lambda: quiet["now"]
    waiter = asyncio.create_task(queue.get())
    await queue.put(SimpleNamespace(priority=0.2, name="first to arrive"))
    await asyncio.sleep(0.05)
    assert not waiter.done()  # a blocked worker no longer grabs the first arrival
    await queue.put(SimpleNamespace(priority=0.9, name="best"))
    quiet["now"] = True
    assert (await asyncio.wait_for(waiter, 2)).name == "best"


def test_merge_writes_graded_labels_the_rubric_hash_and_a_derived_relevant(tmp_path, monkeypatch):
    import json

    from benchmark import FrozenGraph, label_graph

    graph = FrozenGraph(seed="A", pages={
        n: {"title": n, "text": "t", "relevant": None, "links": []} for n in ("A", "B", "C")})
    path = tmp_path / "g.json"
    graph.save(path)
    labels = tmp_path / "labels.jsonl"
    labels.write_text("".join(json.dumps({"page": n, "label": v}) + "\n" for n, v in zip("ABC", (2, 1, 0))))
    monkeypatch.setattr(label_graph, "LABELS", labels)
    label_graph.merge(FrozenGraph.load(path), path)
    data = json.loads(path.read_text())
    assert {n: data["pages"][n]["label"] for n in "ABC"} == {"A": 2, "B": 1, "C": 0}
    assert {n: data["pages"][n]["relevant"] for n in "ABC"} == {"A": True, "B": False, "C": False}
    assert data["rubric_sha256"] == label_graph.rubric_sha()
    assert FrozenGraph.load(path).relevant() == {"A", "B"}  # the runner reads label >= 1


def _audit_graph(n=120):
    from benchmark import FrozenGraph

    pages = {}
    for i in range(n):
        label = 2 if i < 8 else 1 if i < 40 else 0
        where = "en Tunisie" if i % 3 == 0 else "ailleurs"
        pages[f"P{i}"] = {"label": label, "title": f"Page {i}", "text": f"Texte {i} {where}. " * 40,
                          "links": []}
    return FrozenGraph(seed="P0", pages=pages)


def test_audit_sample_is_stratified_blind_and_seeded(tmp_path):
    import csv
    import json

    from benchmark import audit

    graph = _audit_graph()
    path = tmp_path / "g.json"
    graph.save(path)
    pilot = tmp_path / "pilot.tsv"
    pilot.write_text("id\tpage\n1\tP0\n2\tP50\n")
    out, key = tmp_path / "a.tsv", tmp_path / "k.json"
    audit.sample(path, out, key, total=40, seed=3, exclude_files=[pilot])
    rows = list(csv.DictReader(out.open(), delimiter="\t"))
    assert list(rows[0]) == ["id", "title", "excerpt", "human_label"]
    assert all(r["human_label"] == "" and len(r["excerpt"]) <= 450 for r in rows)
    k = json.loads(key.read_text())
    assert len(rows) == 40 and set(k["items"]) == {r["id"] for r in rows}
    pages = {v["page"] for v in k["items"].values()}
    assert "P0" not in pages and "P50" not in pages
    strata = [v["stratum"] for v in k["items"].values()]
    assert strata.count("label2") == 7  # P0 is excluded
    assert all(v["judge_label"] == 2 for v in k["items"].values() if v["stratum"] == "label2")
    assert [r["id"] for r in rows] == [str(i) for i in range(1, 41)]
    first = [v["page"] for v in k["items"].values()]
    audit.sample(path, tmp_path / "b.tsv", tmp_path / "k2.json", total=40, seed=3, exclude_files=[pilot])
    assert first == [v["page"] for v in json.loads((tmp_path / "k2.json").read_text())["items"].values()]


def test_audit_kappa_and_reweighting():
    from benchmark import audit

    perfect = [(0, 0), (1, 1), (2, 2), (0, 0)]
    assert audit.kappa(perfect) == 1.0 and audit.agreement(perfect) == 1.0
    # po = 0.7, pe = 0.3*0.4 + 0.7*0.6 = 0.54
    pairs = [(1, 1)] * 20 + [(0, 0)] * 50 + [(1, 0)] * 10 + [(0, 1)] * 20
    assert abs(audit.kappa(pairs) - 0.16 / 0.46) < 1e-9
    lo, hi = audit.bootstrap_ci(pairs, audit.kappa)
    assert lo < 0.16 / 0.46 < hi
    # judge class 2 is rare in the sample and common in the graph
    pairs = [(2, 2)] * 5 + [(0, 0)] * 5 + [(0, 1)] * 5
    rw, missing = audit.reweighted_agreement(pairs, {0: 10, 1: 5, 2: 85})
    assert missing == [1] and abs(rw - (10 * 0.5 + 85 * 1.0) / 95) < 1e-9
    assert audit.confusion(pairs, (0, 1, 2)) == [[5, 5, 0], [0, 0, 0], [0, 0, 5]]


def test_audit_score_with_two_annotators(tmp_path, capsys):
    import json

    from benchmark import audit

    items = {str(i): {"page": f"P{i}", "stratum": "uniform", "judge_label": i % 3} for i in range(1, 31)}
    (tmp_path / "k.json").write_text(json.dumps(
        {"graph_label_counts": {"0": 60, "1": 30, "2": 10}, "items": items}))
    for name, shift in (("h1.tsv", 0), ("h2.tsv", 1)):
        rows = ["id\ttitle\texcerpt\thuman_label"] + [
            f"{i}\tt\te\t{(i % 3 + (shift if i % 5 == 0 else 0)) % 3}" for i in range(1, 31)]
        (tmp_path / name).write_text("\n".join(rows))
    audit.score(tmp_path / "h1.tsv", tmp_path / "k.json", tmp_path / "h2.tsv")
    out = capsys.readouterr().out
    assert "judge vs annotator 1" in out and "annotator 1 vs annotator 2" in out
    assert "kappa" in out and "reweighted" in out


async def test_cache_key_separates_graph_prompt_version_provider_and_model(tmp_path):
    from benchmark.llm_cache import CachedLlm
    from models.llm_context import LlmContext

    class Inner:
        calls = 0

        async def send(self, context):
            self.calls += 1
            return {"n": self.calls}

    inner = Inner()
    path = tmp_path / "c.jsonl"
    base = dict(prompt_version="TOPICAL:aaa", graph_sha="g1")
    await CachedLlm(inner, path, **base).send(LlmContext("groq", "m", "p"))
    same = CachedLlm(inner, path, **base)
    assert await same.send(LlmContext("groq", "m", "p")) == {"n": 1}
    for other, ctx in (
        (dict(base, graph_sha="g2"), LlmContext("groq", "m", "p")),
        (dict(base, prompt_version="TOPICAL:bbb"), LlmContext("groq", "m", "p")),
        (base, LlmContext("openrouter", "m", "p")),
        (base, LlmContext("groq", "m2", "p")),
    ):
        assert await CachedLlm(inner, path, **other).send(ctx) != {"n": 1}
    assert inner.calls == 5


async def test_absent_page_hits_are_counted_and_the_mode_decides_the_cost():
    from benchmark import FrozenGraph, graph as graph_module

    def build():
        return FrozenGraph(seed="A", pages={
            "A": {"label": 0, "links": [{"to": "GONE", "anchor": "gone"}, {"to": "B", "anchor": "b"}]},
            "B": {"label": 1, "links": [{"to": "C", "anchor": "c"}]},
            "C": {"label": 2, "links": []}})

    assert graph_module.ABSENT_PAGE_HITS == "fail"  # the documented default
    failed = await run_policy(build(), "bfs", 3)
    assert failed.visited == ["A", "B", "C"] and failed.absent_page_hits >= 1
    assert not failed.health.valid

    graph = build()
    original = graph_module.ABSENT_PAGE_HITS
    try:
        graph_module.ABSENT_PAGE_HITS = "free"
        free = await run_policy(graph, "bfs", 3)
        graph_module.ABSENT_PAGE_HITS = "budget"
        paid = await run_policy(build(), "bfs", 3)
    finally:
        graph_module.ABSENT_PAGE_HITS = original
    assert free.visited == ["A", "B", "C"] and free.absent_page_hits == 1 and free.health.valid
    assert "GONE" in paid.visited and paid.absent_page_hits == 1 and len(paid.visited) == 3
    assert paid.labels[paid.visited.index("GONE")] == 0


async def test_every_result_carries_a_manifest(tmp_path):
    import json

    from benchmark import FrozenGraph, synthetic_graph
    from benchmark.provenance import manifest
    from benchmark.results import RunRecord, load_records

    graph = synthetic_graph(n_pages=60, seed=1)
    path = tmp_path / "g.json"
    graph.save(path)
    data = json.loads(path.read_text())
    data["rubric_sha256"] = "abc"
    path.write_text(json.dumps(data))
    result = await run_policy(graph, "bfs", 10)
    assert result.thresholds["mode"] == "none"
    m = manifest(path, graph, result, budget=10, seed=2, rep=2, model="m", provider="p", prompt="TOPICAL:1")
    assert set(m) == {"git_commit", "graph_sha256", "rubric_sha256", "model", "provider", "prompt_version",
                      "budget", "thresholds", "seed", "repeat", "absent_page_mode"}
    assert m["rubric_sha256"] == "abc" and len(m["graph_sha256"]) == 64 and m["git_commit"]
    RunRecord.from_result("g.json", 2, 10, result, manifest=m).filename()
    out = tmp_path / "r"
    out.mkdir()
    (out / "x.json").write_text(json.dumps(RunRecord.from_result("g.json", 2, 10, result, manifest=m).to_json()))
    assert load_records(out)[0].manifest == m
    # a result written before manifests existed still loads
    old = RunRecord.from_result("g.json", 0, 10, result).to_json()
    del old["manifest"], old["absent_page_hits"]
    assert RunRecord.from_json(old).manifest == {}


def test_graph_stats_counts_depths_labels_and_absent_links():
    from benchmark import FrozenGraph
    from benchmark.graph_stats import stats, to_tex

    def link(to):
        return {"to": to, "anchor": to}

    graph = FrozenGraph(seed="A", pages={
        "A": {"label": 0, "links": [link("B"), link("C"), link("GONE")]},
        "B": {"label": 1, "links": [link("D")]},
        "C": {"label": 0, "links": [link("D")]},
        "D": {"label": 2, "links": []},
        "E": {"label": 2, "links": [link("A")]},  # relevant, not reachable from the seed
    })
    s = stats(graph)
    assert (s["pages"], s["edges"], s["absent_links"], s["reachable"]) == (5, 6, 1, 4)
    assert s["out_degree"] == {"mean": 1.2, "median": 1, "max": 3}
    assert s["depth_histogram"] == {0: 1, 1: 2, 2: 1}
    assert s["labels"] == {0: 2, 1: 1, 2: 2}
    assert s["relevant_per_depth"][1] == {"pages": 2, "label1": 1, "label2": 0}
    assert s["relevant_per_depth"][2]["label2"] == 1
    assert s["relevant_unreachable"] == 1
    assert r"\begin{tabular}" in to_tex(s)


def _record(policy, rep, labels, graph="g.json", valid=True, status="completed", **kw):
    from benchmark.results import RunRecord

    return RunRecord(graph=graph, policy=policy, rep=rep, budget=len(labels), sequence=[f"p{i}" for i in labels],
                     labels=labels, valid=valid, status=status, **kw)


def test_analyze_metrics_on_known_runs(tmp_path):
    import math

    from benchmark import analyze

    labels = [2, 0, 1, 0]
    assert analyze.harvest_at(labels, 4) == 0.5
    assert analyze.harvest_at(labels, 4, min_grade=2) == 0.25
    assert analyze.recall_at(labels, 3, relevant_in_graph=10) == 0.2
    assert math.isnan(analyze.recall_at(labels, 3, 0))
    grades = {0: 50, 1: 2, 2: 1}  # ideal order 2, 1, 1
    ideal = 2 / 1 + 1 / math.log2(3) + 1 / 2
    got = 2 / 1 + 1 / math.log2(4)  # the run's [2, 0, 1]
    assert abs(analyze.ndcg_at(labels, 3, grades) - got / ideal) < 1e-9
    assert analyze.ndcg_at([2, 1, 1], 3, grades) == 1.0

    run = _record("cascade", 0, [1, 1, 0, 2], llm_calls=3, llm_replayed=1, input_tokens=1500, output_tokens=500)
    assert analyze.efficiency(run) == (3 / 4, 3 / 2.0)
    assert math.isnan(analyze.efficiency(_record("bfs", 0, [1]))[0])

    records = [run, _record("cascade", 1, [0, 0], valid=False, status="failed"),
               _record("bfs", 0, [1], status="completed_early"),
               _record("cascade", 2, [1], replay=True, replay_misses=2, valid=False, status="failed")]
    assert analyze.validity_counts(records) == {
        "cascade": {"valid": 1, "invalid": 1, "early": 0}, "bfs": {"valid": 1, "invalid": 0, "early": 1}}
    assert analyze.replay_counts(records) == {"cascade": {"replays": 1, "with_misses": 1, "misses": 2}}
    for tex in (analyze.validity_table_tex(records), analyze.replay_table_tex(records),
                analyze.efficiency_table_tex(analyze.by_policy(records))):
        assert tex.count(r"\begin{tabular}") == 1 and r"\end{tabular}" in tex

    (tmp_path / "g.json").write_text('{"seed": "a", "pages": {"a": {"label": 2}, "b": {"relevant": true}, "c": {"label": 0}}}')
    assert analyze.graph_grades(tmp_path, "g.json") == {0: 1, 1: 1, 2: 1}
    assert analyze.graph_grades(tmp_path, "missing.json") is None


def test_failed_replay_does_not_overwrite_the_live_record(tmp_path):
    from benchmark.results import ResultSink, load_records

    sink = ResultSink(tmp_path)
    sink.add(_record("cascade", 0, [1, 2]))
    sink.add(_record("cascade", 0, [1, 2], replay=True, replay_misses=3, valid=False, status="failed"))
    sink.add(_record("cascade", 0, [1, 2], replay=True, llm_replayed=9))
    recs = load_records(tmp_path)
    assert sorted((r.replay, r.replay_misses, r.valid) for r in recs) == [
        (False, 0, True), (True, 0, True), (True, 3, False)]
    live = [r for r in recs if not r.replay]
    assert len(live) == 1 and live[0].llm_replayed == 0  # the live record is intact
    from benchmark import analyze

    assert list(analyze.by_policy(recs)["cascade"]) == live  # replays are not extra samples
    assert analyze.validity_counts(recs) == {"cascade": {"valid": 1, "invalid": 0, "early": 0}}


def test_analyze_main_writes_every_table(tmp_path, monkeypatch, capsys):
    import json
    import sys

    from benchmark import analyze
    from benchmark.results import ResultSink

    (tmp_path / "g.json").write_text(json.dumps({"seed": "a", "pages": {
        f"p{i}": {"label": 2 if i < 3 else 1 if i < 8 else 0, "links": []} for i in range(30)}}))
    sink = ResultSink(tmp_path / "res")
    for rep in range(6):
        sink.add(_record("cascade", rep, [2, 1, 1, 0, 1] * 8, llm_calls=10, input_tokens=4000, output_tokens=1000))
        sink.add(_record("bfs", rep, [0, 1, 0, 0, 0] * 8 if rep % 2 else [0, 0, 0, 1, 0] * 8))
    sink.add(_record("cascade", 9, [0], valid=False, status="failed"))
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["analyze", "--results", str(tmp_path / "res"), "--out", str(out),
                                      "--graphs-dir", str(tmp_path), "--no-dedupe", "--ndcg"])
    analyze.main()
    names = {p.name for p in out.iterdir()}
    assert {"curves.csv", "harvest_table.tex", "harvest_label2_table.tex", "recall_table.tex",
            "efficiency_table.tex", "validity_table.tex", "replay_table.tex", "ndcg_table.tex",
            "wilcoxon_table.tex"} <= names
    printed = capsys.readouterr().out
    assert "cascade vs bfs" in printed and "6/1/0" in printed
    assert "--" not in (out / "recall_table.tex").read_text().split(r"\midrule")[1].split(r"\bottomrule")[0]


def test_grading_problems_flag_ungraded_and_sparse_graphs():
    from benchmark import FrozenGraph

    def graph(labels):
        return FrozenGraph(seed="p0", pages={
            f"p{i}": {**({"label": v} if v is not None else {"relevant": False}), "links": []}
            for i, v in enumerate(labels)})

    assert "no 0/1/2 label" in graph([None, 0, 1]).grading_problems()[0]
    assert "no label-2" in " ".join(graph([0] * 5 + [1] * 40).grading_problems())
    assert "only 3 relevant" in " ".join(graph([0, 1, 2, 2]).grading_problems())
    assert graph([0] * 5 + [1] * 30 + [2] * 3).grading_problems() == []


def test_audit_sample_refuses_a_graph_without_judge_labels(tmp_path):
    import pytest

    from benchmark import FrozenGraph, audit

    path = tmp_path / "g.json"
    FrozenGraph(seed="a", pages={"a": {"relevant": None, "title": "A", "text": "t", "links": []}}).save(path)
    with pytest.raises(SystemExit, match="no judge label"):
        audit.sample(path, tmp_path / "o.tsv", tmp_path / "k.json", total=None, seed=0, exclude_files=[])


def test_cli_refuses_an_ungraded_graph_before_running_anything(tmp_path):
    import subprocess
    import sys

    from benchmark import FrozenGraph

    path = tmp_path / "g.json"
    FrozenGraph(seed="a", pages={"a": {"relevant": True, "links": []}}).save(path)
    run = subprocess.run([sys.executable, "-m", "benchmark", "--graph", str(path), "--budget", "1"],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode != 0 and "cannot support a graded comparison" in run.stderr
