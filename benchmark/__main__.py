"""python -m benchmark [--graph FILE] [--budget N] [--runs R]

Without --graph, R synthetic graphs (seeds 0..R-1) are generated. Prints, per
policy, relevant pages found within the budget (mean and standard deviation
over the runs) and the share of the fetched pages that were relevant
(label >= 1), plus the mean number of direct targets (label 2) found.
"""
import argparse
import asyncio
import json
import statistics
import tempfile
from pathlib import Path

from .graph import FrozenGraph, synthetic_graph
from .policies import POLICIES
from .provenance import manifest
from .results import ResultSink, RunRecord
from .runner import run_cascade, run_policy


async def main(args) -> None:
    graphs = (
        [FrozenGraph.load(args.graph)]
        if args.graph
        else [synthetic_graph(n_pages=args.pages, seed=s) for s in range(args.runs)]
    )
    if args.cascade and not args.graph:
        raise SystemExit("--cascade needs a recorded, labelled --graph")
    sink = ResultSink(args.results_dir, args.save_sequences)
    print(f"{len(graphs)} graph(s), budget {args.budget} pages\n")
    print(f"{'policy':<16}{'found (mean)':>14}{'sd':>8}{'harvest':>10}{'direct':>8}   per run")
    for name in POLICIES:
        runs = []
        for gi, graph in enumerate(graphs):
            for rep in range(args.reps):
                result = await run_policy(graph, name, args.budget, seed=rep)
                runs.append(result)
                sink.add(RunRecord.from_result(
                    graph_name(args, gi), rep, args.budget, result,
                    manifest=manifest(args.graph, graph, result, budget=args.budget, seed=rep, rep=rep),
                ))
        report(name, runs, args.budget)
    if args.cascade:
        await cascade_row(graphs, args, sink)


def graph_name(args, index: int) -> str:
    return Path(args.graph).name if args.graph else f"synthetic{index}"


def report(name: str, runs: list, budget: int) -> None:
    """One row: mean and sd over the *valid* runs, every valid value, and what was left out."""
    valid = [r for r in runs if r.health.valid]
    found = [r.found(budget) for r in valid]
    sd = statistics.stdev(found) if len(found) > 1 else 0.0
    mean = statistics.mean(found) if found else float("nan")
    direct = statistics.mean(r.found_direct(budget) for r in valid) if valid else float("nan")
    values = " ".join(str(f) for f in found)
    print(f"{name:<16}{mean:>14.1f}{sd:>8.1f}{mean / budget:>10.0%}{direct:>8.1f}   [{values}]", end="")
    print(f"   {len(valid)}/{len(runs)} valid" if len(valid) != len(runs) else "")
    for i, r in enumerate(runs):
        if r.health.status == "completed_early":
            print(f"    run {i} completed early: {len(r.visited)} of {budget} pages ({r.health.reason}), kept")
        if not r.health.valid:
            print(f"    run {i} INVALID, excluded: {'; '.join(r.health.problems)}")


async def cascade_row(graphs, args, sink: ResultSink) -> None:
    """The real cascade; needs a labelled recorded graph and the blueprint's settings."""
    from infrastructure import KeyManager, LlmHandler

    from .llm_cache import CachedLlm, PacedLlm, ReplayMiss
    from .provenance import file_sha256, prompt_version

    bp = json.loads(Path(args.template).read_text())
    # The provider is stated here, not read from the template: the template names
    # OpenRouter, and the cascade and the judge should not share a model family.
    expansion = {**bp["expansion"], "llm_type": args.provider, "llm_model": args.model}
    params = {"scoring_type": args.provider, "model_information": args.model}
    arm = "llm_all" if args.llm_all else "no_llm" if args.no_llm else "cascade"
    name = arm + (f"_low{args.low}" if args.low is not None else "") + (f"_high{args.high}" if args.high is not None else "")
    name += (f"_lowpct{args.low_pct:g}" if args.low_pct is not None else "") + (
        f"_highpct{args.high_pct:g}" if args.high_pct is not None else "")
    # no_llm replays the recorded expansion and makes no scoring call, so it
    # never talks to a provider; every other arm does unless replaying.
    offline = args.replay_only or arm == "no_llm"
    live = None if offline else PacedLlm(LlmHandler(KeyManager(keys_file=Path("keys.json"))))
    # The cache key carries the model, provider, prompt version and graph hash
    # (besides the prompt), so an answer is never replayed for another graph or prompt.
    cache_id = dict(prompt_version=prompt_version(bp["scoring"]["strategy"]), graph_sha=file_sha256(args.graph))
    recorded = json.loads(Path(args.runs_file).read_text()) if Path(args.runs_file).exists() else {}
    runs = []
    for graph in graphs:
        for rep in range(args.reps):
            # One cache scope per repeat: independent live LLM realizations
            # the first time, an exact replay of the same repeat afterwards.
            calls_before, waits_before, limits_before = (
                (len(live.latencies), live.wait_seconds, live.rate_limit_seconds) if live else (0, 0.0, 0.0)
            )
            llm = CachedLlm(live, args.llm_cache, scope=f"rep{rep}", replay_only=offline, **cache_id)
            # And one space store per repeat: NLPService loads a saved topic
            # space instead of expanding the topic again, which would make
            # repeat 1 inherit repeat 0's expansion.
            with tempfile.TemporaryDirectory() as store:
                result = await run_cascade(
                    graph, args.budget, rep, llm, bp["extraction"], expansion,
                    bp["scoring"]["strategy"],
                    (params["scoring_type"], params["model_information"]), store,
                    flush_every=args.flush_every, arm=arm, low=args.low, high=args.high,
                    low_pct=args.low_pct, high_pct=args.high_pct,
                )
            result.policy = name
            h = result.health
            if llm.replay_misses:  # the pipeline may have swallowed ReplayMiss
                # Kept for the analysis' replay table, under its own file name.
                h.problems.append(f"{len(llm.replay_misses)} replay cache miss(es)")
                sink.add(RunRecord.from_result(
                    Path(args.graph).name, rep, args.budget, result, replay=True,
                    replay_misses=len(llm.replay_misses), llm_replayed=llm.hits,
                ))
                raise ReplayMiss(f"rep {rep}: {len(llm.replay_misses)} LLM lookups were not recorded")
            latencies = live.latencies[calls_before:] if live else []
            waited = live.wait_seconds - waits_before if live else 0.0
            limited = live.rate_limit_seconds - limits_before if live else 0.0
            runkey = f"{Path(args.graph).name}:budget{args.budget}:flush{args.flush_every}:rep{rep}"
            if name != "cascade":  # the plain cascade keeps its original key
                runkey += f":{name}"
            if args.replay_only:
                if runkey not in recorded:
                    raise RuntimeError(f"{runkey}: no recorded run to compare the replay against")
                if recorded[runkey]["visited"] != result.visited:
                    was, now = recorded[runkey]["visited"], result.visited
                    at = next((i for i, (a, b) in enumerate(zip(was, now)) if a != b), min(len(was), len(now)))
                    raise RuntimeError(
                        f"{runkey}: replay visited a different page sequence than the original run; "
                        f"first difference at fetch {at}: original {was[at:at + 2]}, replay {now[at:at + 2]}"
                    )
                live_wall = recorded[runkey]["wall_seconds"]
                note = (
                    f"replay matches the original; wall {result.wall_seconds:.1f}s vs {live_wall:.1f}s live "
                    f"(LLM, pacing and rate limits account for about {live_wall - result.wall_seconds:.1f}s)"
                )
            else:
                note = "recorded"
                if h.valid:
                    recorded[runkey] = {"visited": result.visited, "wall_seconds": result.wall_seconds}
            print(
                f"  cascade rep {rep}: found {result.found(args.budget)}, "
                f"{'valid' if h.valid else 'INVALID'}; "
                f"{llm.misses} live LLM calls, {llm.hits} replayed; "
                f"scored {h.nodes_scored}/{h.nodes_fetched} fetched; "
                f"LLM failures handled {h.scoring_failures}, empty answers handled {h.empty_results}"
                + (f", rate-limit waits {live.rate_limit_waits}" if live else "")
                + (f"; {note}" if h.valid else "")
            )
            if latencies:
                ordered = sorted(latencies)
                p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
                llm_time = sum(latencies)
                print(
                    f"    timing: wall {result.wall_seconds:.1f}s, {len(result.visited) / result.wall_seconds:.2f} pages/s; "
                    f"LLM latency mean {statistics.mean(latencies):.1f}s median {statistics.median(latencies):.1f}s "
                    f"p95 {p95:.1f}s ({len(latencies)} calls, {llm_time:.0f}s total); "
                    f"waiting on pacing and rate limits {waited:.0f}s (429 back-off {limited:.0f}s, idle clock paused); "
                    f"everything else {max(0.0, result.wall_seconds - llm_time - waited):.0f}s"
                )
            print(f"    tokens: {llm.input_tokens} in, {llm.output_tokens} out over {llm.misses + llm.hits} answers")
            sink.add(RunRecord.from_result(
                Path(args.graph).name, rep, args.budget, result,
                llm_calls=llm.misses, llm_replayed=llm.hits, replay=bool(args.replay_only),
                input_tokens=llm.input_tokens, output_tokens=llm.output_tokens,
                llm_seconds=round(sum(latencies), 3), wait_seconds=round(waited, 3),
                rate_limit_waits=live.rate_limit_waits if live else 0,
                rate_limit_seconds=round(limited, 3),
                manifest=manifest(
                    args.graph, graph, result, budget=args.budget, seed=rep, rep=rep,
                    model=args.model, provider=args.provider, prompt=cache_id["prompt_version"],
                ),
                settings={"flush_every": args.flush_every, "provider": args.provider, "model": args.model,
                          "arm": arm, "low": args.low, "high": args.high,
                          "low_pct": args.low_pct, "high_pct": args.high_pct},
            ))
            runs.append(result)
    if live:
        await live.client.close()
        Path(args.runs_file).write_text(json.dumps(recorded))
    report(name, runs, args.budget)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", help="frozen graph JSON (default: synthetic)")
    parser.add_argument("--budget", type=int, default=100)
    parser.add_argument("--runs", type=int, default=5, help="synthetic graphs to generate")
    parser.add_argument("--reps", type=int, default=1, help="repeats per graph (policy seeds)")
    parser.add_argument("--pages", type=int, default=600)
    parser.add_argument("--cascade", action="store_true", help="also run the real cascade (needs --graph)")
    parser.add_argument("--template", default="templates/isi.json", help="blueprint for the cascade's settings")
    parser.add_argument("--llm-cache", default="benchmark/data/cascade_cache.jsonl")
    parser.add_argument("--provider", default="groq", help="LLM provider for the cascade (keys.json section)")
    parser.add_argument("--model", default="openai/gpt-oss-120b", help="LLM model for the cascade")
    parser.add_argument("--runs-file", default="benchmark/data/cascade_runs.json",
                        help="page sequences of completed repeats, which a replay must reproduce")
    parser.add_argument("--replay-only", action="store_true",
                        help="no live LLM calls: any unrecorded lookup fails, and every repeat must reproduce its recorded run")
    parser.add_argument("--flush-every", type=int, default=8,
                        help="commit semantic-space growth after this many scored nodes (production: a 60s timer, about 8 nodes at the scoring pace measured live)")
    parser.add_argument("--llm-all", action="store_true",
                        help="cascade arm: every discovered link goes to the LLM (same prompt and batch size), no embedding filter")
    parser.add_argument("--no-llm", action="store_true",
                        help="cascade arm: embedding scores only; the topic expansion is replayed from --llm-cache")
    parser.add_argument("--low-pct", type=float, metavar="PCT",
                        help="percentile bucketing, the DEFAULT mode: a node's links below this percentile of "
                             "its own scores are low (default 20)")
    parser.add_argument("--high-pct", type=float, metavar="PCT",
                        help="percentile bucketing: links above this percentile are high (default 75)")
    parser.add_argument("--low", type=float,
                        help="absolute-threshold mode (not the default): scores below this are low (config 0.20); "
                             "turns percentile bucketing off, so it excludes --low-pct/--high-pct")
    parser.add_argument("--high", type=float,
                        help="absolute-threshold mode (not the default): scores above this are high (config 0.75)")
    parser.add_argument("--results-dir", default="benchmark/results",
                        help="one JSON file per policy run (sequence, labels, calls, tokens, timings, validity)")
    parser.add_argument("--save-sequences", metavar="FILE",
                        help="write the full visit order of every policy and repeat, baselines included")
    options = parser.parse_args()
    if options.llm_all and options.no_llm:
        parser.error("--llm-all and --no-llm are different arms; pick one")
    absolute = options.low is not None or options.high is not None
    percentile = options.low_pct is not None or options.high_pct is not None
    if absolute and percentile:
        parser.error("--low/--high (absolute thresholds) and --low-pct/--high-pct (percentiles) are different modes")
    if (options.llm_all or options.no_llm) and (absolute or percentile):
        parser.error("--low/--high and --low-pct/--high-pct apply to the plain cascade only")
    if (options.llm_all or options.no_llm or absolute or percentile) and not options.cascade:
        parser.error("--llm-all, --no-llm and the threshold flags modify the cascade run; add --cascade")
    asyncio.run(main(options))
