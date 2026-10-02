"""python -m benchmark [--graph FILE] [--budget N] [--runs R]

Without --graph, R synthetic graphs (seeds 0..R-1) are generated. Prints, per
policy, relevant pages found within the budget (mean and standard deviation
over the runs) and the share of the fetched pages that were relevant.
"""
import argparse
import asyncio
import json
import statistics
import tempfile
from pathlib import Path

from .graph import FrozenGraph, synthetic_graph
from .policies import POLICIES
from .runner import run_cascade, run_policy


async def main(args) -> None:
    graphs = (
        [FrozenGraph.load(args.graph)]
        if args.graph
        else [synthetic_graph(n_pages=args.pages, seed=s) for s in range(args.runs)]
    )
    if args.cascade and not args.graph:
        raise SystemExit("--cascade needs a recorded, labelled --graph")
    print(f"{len(graphs)} graph(s), budget {args.budget} pages\n")
    print(f"{'policy':<16}{'found (mean)':>14}{'sd':>8}{'harvest':>10}   per run")
    for name in POLICIES:
        runs = []
        for graph in graphs:
            for rep in range(args.reps):
                runs.append(await run_policy(graph, name, args.budget, seed=rep))
        report(name, runs, args.budget)
    if args.cascade:
        await cascade_row(graphs, args)


def report(name: str, runs: list, budget: int) -> None:
    """One row: mean and sd over the *valid* runs, every valid value, and what was left out."""
    valid = [r for r in runs if r.health.valid]
    found = [r.found(budget) for r in valid]
    sd = statistics.stdev(found) if len(found) > 1 else 0.0
    mean = statistics.mean(found) if found else float("nan")
    values = " ".join(str(f) for f in found)
    print(f"{name:<16}{mean:>14.1f}{sd:>8.1f}{mean / budget:>10.0%}   [{values}]", end="")
    print(f"   {len(valid)}/{len(runs)} valid" if len(valid) != len(runs) else "")
    for i, r in enumerate(runs):
        if r.health.status == "completed_early":
            print(f"    run {i} completed early: {len(r.visited)} of {budget} pages ({r.health.reason}), kept")
        if not r.health.valid:
            print(f"    run {i} INVALID, excluded: {'; '.join(r.health.problems)}")


async def cascade_row(graphs, args) -> None:
    """The real cascade; needs a labelled recorded graph and the blueprint's settings."""
    from infrastructure import KeyManager, LlmHandler

    from .llm_cache import CachedLlm, PacedLlm, ReplayMiss

    bp = json.loads(Path(args.template).read_text())
    # The provider is stated here, not read from the template: the template names
    # OpenRouter, and the cascade and the judge should not share a model family.
    expansion = {**bp["expansion"], "llm_type": args.provider, "llm_model": args.model}
    params = {"scoring_type": args.provider, "model_information": args.model}
    live = None if args.replay_only else PacedLlm(LlmHandler(KeyManager(keys_file=Path("keys.json"))))
    recorded = json.loads(Path(args.runs_file).read_text()) if Path(args.runs_file).exists() else {}
    runs = []
    for graph in graphs:
        for rep in range(args.reps):
            # One cache scope per repeat: independent live LLM realizations
            # the first time, an exact replay of the same repeat afterwards.
            calls_before, waits_before = (len(live.latencies), live.wait_seconds) if live else (0, 0.0)
            llm = CachedLlm(live, args.llm_cache, scope=f"rep{rep}", replay_only=args.replay_only)
            # And one space store per repeat: NLPService loads a saved topic
            # space instead of expanding the topic again, which would make
            # repeat 1 inherit repeat 0's expansion.
            with tempfile.TemporaryDirectory() as store:
                result = await run_cascade(
                    graph, args.budget, rep, llm, bp["extraction"], expansion,
                    bp["scoring"]["strategy"],
                    (params["scoring_type"], params["model_information"]), store,
                    flush_every=args.flush_every,
                )
            h = result.health
            if llm.replay_misses:  # the pipeline may have swallowed ReplayMiss
                raise ReplayMiss(f"rep {rep}: {len(llm.replay_misses)} LLM lookups were not recorded")
            latencies = live.latencies[calls_before:] if live else []
            waited = live.wait_seconds - waits_before if live else 0.0
            runkey = f"{Path(args.graph).name}:budget{args.budget}:flush{args.flush_every}:rep{rep}"
            if args.replay_only:
                if runkey not in recorded:
                    raise RuntimeError(f"{runkey}: no recorded run to compare the replay against")
                if recorded[runkey]["visited"] != result.visited:
                    raise RuntimeError(f"{runkey}: replay visited a different page sequence than the original run")
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
                    f"waiting on pacing and rate limits {waited:.0f}s; "
                    f"everything else {max(0.0, result.wall_seconds - llm_time - waited):.0f}s. "
                    "Token usage is not available: the translators discard it."
                )
            runs.append(result)
    if live:
        await live.client.close()
        Path(args.runs_file).write_text(json.dumps(recorded))
    report("cascade", runs, args.budget)


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
    asyncio.run(main(parser.parse_args()))
