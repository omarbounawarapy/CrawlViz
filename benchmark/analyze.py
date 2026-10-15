"""python -m benchmark.analyze [--results DIR] [--out DIR] [--k 100] [--test-k 30]

Reads the per-run JSON files (benchmark.results) and writes, to ``--out``:

Pages that share a title are one article under several names (redirects):
with ``--graphs-dir`` each title counts once, at its first visit, before
harvest@k is computed.

* ``curves.csv``: harvest@k for k = 1..K, per policy: mean and 95% CI
* ``harvest_table.tex``: harvest at chosen k (label >= 1), mean +/- 95% CI, per policy
* ``harvest_label2_table.tex``: the same for direct targets only (label == 2)
* ``recall_table.tex``: exact recall@k, relevant pages fetched over relevant
  pages in the graph (needs the graph file in ``--graphs-dir``)
* ``efficiency_table.tex``: relevant pages found per LLM call and per 1k tokens
  (answers served from the cache count at the calls and tokens they cost)
* ``validity_table.tex``: valid / invalid / early-stopped runs per policy
* ``replay_table.tex``: replayed runs and their cache misses per policy
* ``ndcg_table.tex``: with ``--ndcg``, nDCG@k of the fetch order, grades 0/1/2
  as gains; the ideal order is the whole graph's best k pages
* ``wilcoxon_table.tex``: paired Wilcoxon signed-rank test of the cascade
  against every other policy on harvest@``--test-k``

Invalid runs are excluded from every table except validity and replay.
Replay records (``__replay.json``) are only used by the replay table. Runs
are paired on (graph, repeat).
"""
import argparse
import csv
import math
import statistics
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from scipy import stats

from .results import RunRecord, load_records

TABLE_KS = (10, 30, 50, 100)


def harvest_at(labels: list[int], k: int, min_grade: int = 1) -> float:
    """Share of the first k fetched pages graded at least ``min_grade``."""
    head = labels[:k]
    return sum(1 for v in head if v >= min_grade) / len(head) if head else 0.0


def recall_at(labels: list[int], k: int, relevant_in_graph: int) -> float:
    """Relevant (label >= 1) pages among the first k fetched, over all in the graph."""
    if not relevant_in_graph:
        return float("nan")
    return sum(1 for v in labels[:k] if v >= 1) / relevant_in_graph


def ndcg_at(labels: list[int], k: int, graph_grades: dict[int, int]) -> float:
    """nDCG@k with the grade as gain. The ideal order is the graph's best k
    pages (all label 2, then label 1), which no crawler is promised to reach."""
    def dcg(grades) -> float:
        return sum(g / math.log2(i + 2) for i, g in enumerate(grades))

    ideal = [2] * graph_grades.get(2, 0) + [1] * graph_grades.get(1, 0)
    best = dcg(ideal[:k])
    return dcg(labels[:k]) / best if best else float("nan")


def graph_grades(graphs_dir: Path, name: str, _cache: dict = {}) -> dict[int, int] | None:
    """Count of pages per grade in a graph file, or None if the file is missing."""
    import json

    path = graphs_dir / name
    if not path.is_file():
        return None
    if path not in _cache:
        counts = {0: 0, 1: 0, 2: 0}
        for page in json.loads(path.read_text())["pages"].values():
            label = page.get("label")
            counts[int(label) if label is not None else 1 if page.get("relevant") else 0] += 1
        _cache[path] = counts
    return _cache[path]


def dedupe_by_title(record: RunRecord, titles: dict[str, str]) -> RunRecord:
    """The run with every repeated title after its first visit removed."""
    seen: set[str] = set()
    sequence, labels = [], []
    for name, label in zip(record.sequence, record.labels):
        key = titles.get(name, name)
        if key in seen:
            continue
        seen.add(key)
        sequence.append(name)
        labels.append(label)
    return replace(record, sequence=sequence, labels=labels)


def load_titles(graph_file: Path) -> dict[str, str]:
    import json

    pages = json.loads(graph_file.read_text())["pages"]
    from .graph import page_key

    return {page_key(n): p["title"] for n, p in pages.items() if p.get("title")}


def dedupe_records(records: list[RunRecord], graphs_dir: Path) -> list[RunRecord]:
    cache: dict[str, dict[str, str]] = {}
    out = []
    for r in records:
        path = graphs_dir / r.graph
        if r.graph not in cache:
            cache[r.graph] = load_titles(path) if path.is_file() else {}
        out.append(dedupe_by_title(r, cache[r.graph]) if cache[r.graph] else r)
    return out


def mean_ci(values: list[float]) -> tuple[float, float]:
    """Mean and the half-width of the 95% Student-t confidence interval."""
    if not values:
        return float("nan"), float("nan")
    mean = statistics.mean(values)
    if len(values) < 2:
        return mean, float("nan")
    sem = statistics.stdev(values) / math.sqrt(len(values))
    return mean, stats.t.ppf(0.975, len(values) - 1) * sem


def by_policy(records: list[RunRecord]) -> dict[str, list[RunRecord]]:
    groups: dict[str, list[RunRecord]] = defaultdict(list)
    for r in records:
        if r.valid and not r.replay:  # a replay repeats a live run; it is not another sample
            groups[r.policy].append(r)
    return dict(groups)


def curves(groups: dict[str, list[RunRecord]], max_k: int) -> list[tuple[str, int, float, float, int]]:
    rows = []
    for policy, runs in groups.items():
        for k in range(1, max_k + 1):
            mean, ci = mean_ci([harvest_at(r.labels, k) for r in runs])
            rows.append((policy, k, mean, ci, len(runs)))
    return rows


def wilcoxon(groups: dict[str, list[RunRecord]], k: int, subject: str = "cascade") -> list[dict]:
    """Subject against every other policy, paired on (graph, repeat)."""
    if subject not in groups:
        return []
    mine = {(r.graph, r.rep): harvest_at(r.labels, k) for r in groups[subject]}
    out = []
    for policy, runs in groups.items():
        if policy == subject:
            continue
        theirs = {(r.graph, r.rep): harvest_at(r.labels, k) for r in runs}
        pairs = sorted(set(mine) & set(theirs))
        a = [mine[p] for p in pairs]
        b = [theirs[p] for p in pairs]
        diffs = [x - y for x, y in zip(a, b)]
        if not diffs or all(d == 0 for d in diffs):
            p_value = float("nan") if not diffs else 1.0
        else:
            p_value = float(stats.wilcoxon(a, b).pvalue)
        out.append({
            "policy": policy, "n": len(pairs),
            "subject_mean": statistics.mean(a) if a else float("nan"),
            "other_mean": statistics.mean(b) if b else float("nan"),
            "p": p_value,
        })
    return out


def _tex(text: str) -> str:
    return text.replace("_", r"\_")


def metric_table_tex(groups: dict[str, list[RunRecord]], value, ks=TABLE_KS) -> str:
    """Mean +/- 95% CI of ``value(run, k)`` per policy at each k; runs with a
    NaN value (a metric that needs a missing graph file) are left out."""
    head = " & ".join(f"@{k}" for k in ks)
    lines = [r"\begin{tabular}{l" + "c" * len(ks) + "r}", r"\toprule",
             f"Policy & {head} & runs \\\\", r"\midrule"]
    for policy, runs in groups.items():
        cells = []
        for k in ks:
            vals = [v for v in (value(r, k) for r in runs) if not math.isnan(v)]
            mean, ci = mean_ci(vals)
            cells.append("--" if not vals else f"{mean:.3f}" + ("" if math.isnan(ci) else f" $\\pm$ {ci:.3f}"))
        lines.append(f"{_tex(policy)} & " + " & ".join(cells) + f" & {len(runs)} \\\\")
    return "\n".join(lines + [r"\bottomrule", r"\end{tabular}", ""])


def harvest_table_tex(groups: dict[str, list[RunRecord]], ks=TABLE_KS, min_grade: int = 1) -> str:
    return metric_table_tex(groups, lambda r, k: harvest_at(r.labels, k, min_grade), ks)


def efficiency(run: RunRecord) -> tuple[float, float]:
    """(relevant per LLM call, relevant per 1k tokens); NaN for a run with none."""
    found = sum(1 for v in run.labels if v >= 1)
    calls = run.llm_calls + run.llm_replayed
    tokens = run.input_tokens + run.output_tokens
    return (found / calls if calls else float("nan"), found / (tokens / 1000) if tokens else float("nan"))


def efficiency_table_tex(groups: dict[str, list[RunRecord]]) -> str:
    lines = [r"\begin{tabular}{lrrrr}", r"\toprule",
             r"Policy & LLM calls & tokens & relevant / call & relevant / 1k tokens \\", r"\midrule"]
    for policy, runs in groups.items():
        per_call = [e[0] for e in map(efficiency, runs) if not math.isnan(e[0])]
        per_tok = [e[1] for e in map(efficiency, runs) if not math.isnan(e[1])]
        calls = statistics.mean(r.llm_calls + r.llm_replayed for r in runs)
        tokens = statistics.mean(r.input_tokens + r.output_tokens for r in runs)

        def cell(vals):
            mean, ci = mean_ci(vals)
            return "--" if not vals else f"{mean:.3f}" + ("" if math.isnan(ci) else f" $\\pm$ {ci:.3f}")

        lines.append(f"{_tex(policy)} & {calls:.0f} & {tokens:.0f} & {cell(per_call)} & {cell(per_tok)} \\\\")
    return "\n".join(lines + [r"\bottomrule", r"\end{tabular}", ""])


def validity_counts(records: list[RunRecord]) -> dict[str, dict[str, int]]:
    """policy -> valid / invalid / early (completed_early; valid, and counted in ``valid``)."""
    out: dict[str, dict[str, int]] = {}
    for r in records:
        if r.replay:
            continue
        row = out.setdefault(r.policy, {"valid": 0, "invalid": 0, "early": 0})
        row["valid" if r.valid else "invalid"] += 1
        row["early"] += r.status == "completed_early"
    return out


def validity_table_tex(records: list[RunRecord]) -> str:
    lines = [r"\begin{tabular}{lrrrr}", r"\toprule",
             r"Policy & runs & valid & invalid & early-stopped \\", r"\midrule"]
    for policy, c in validity_counts(records).items():
        lines.append(f"{_tex(policy)} & {c['valid'] + c['invalid']} & {c['valid']} & {c['invalid']} & {c['early']} \\\\")
    return "\n".join(lines + [r"\bottomrule", r"\end{tabular}", ""])


def replay_counts(records: list[RunRecord]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for r in records:
        if not r.replay:
            continue
        row = out.setdefault(r.policy, {"replays": 0, "with_misses": 0, "misses": 0})
        row["replays"] += 1
        row["misses"] += r.replay_misses
        row["with_misses"] += r.replay_misses > 0
    return out


def replay_table_tex(records: list[RunRecord]) -> str:
    lines = [r"\begin{tabular}{lrrr}", r"\toprule",
             r"Policy & replays & with misses & cache misses \\", r"\midrule"]
    for policy, c in replay_counts(records).items():
        lines.append(f"{_tex(policy)} & {c['replays']} & {c['with_misses']} & {c['misses']} \\\\")
    return "\n".join(lines + [r"\bottomrule", r"\end{tabular}", ""])


def wilcoxon_table_tex(rows: list[dict], k: int) -> str:
    lines = [r"\begin{tabular}{lrrrr}", r"\toprule",
             f"Baseline & pairs & cascade @{k} & baseline @{k} & $p$ \\\\", r"\midrule"]
    for r in rows:
        p = "--" if math.isnan(r["p"]) else (f"{r['p']:.4f}" if r["p"] >= 0.0001 else "<0.0001")
        lines.append(
            f"{_tex(r['policy'])} & {r['n']} & {r['subject_mean']:.3f} & {r['other_mean']:.3f} & {p} \\\\"
        )
    return "\n".join(lines + [r"\bottomrule", r"\end{tabular}", ""])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results", type=Path, default=Path("benchmark/results"))
    ap.add_argument("--out", type=Path, default=Path("benchmark/analysis"))
    ap.add_argument("--graphs-dir", type=Path, default=Path("benchmark/data"),
                    help="where the graph files named in the results live; each title counts once")
    ap.add_argument("--no-dedupe", action="store_true", help="count every fetched page, duplicates included")
    ap.add_argument("--k", type=int, default=100, help="curves run from 1 to this k")
    ap.add_argument("--test-k", type=int, default=30, help="k for the Wilcoxon tests")
    ap.add_argument("--ndcg", action="store_true", help="also write nDCG@k (needs the graph files)")
    args = ap.parse_args()

    records = load_records(args.results)
    if not args.no_dedupe:
        records = dedupe_records(records, args.graphs_dir)
    groups = by_policy(records)
    if not groups:
        raise SystemExit(f"no valid runs in {args.results}")
    live = [r for r in records if not r.replay]
    skipped = len(live) - sum(len(v) for v in groups.values())
    args.out.mkdir(parents=True, exist_ok=True)

    with (args.out / "curves.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["policy", "k", "mean", "ci95", "runs"])
        for policy, k, mean, ci, n in curves(groups, args.k):
            w.writerow([policy, k, f"{mean:.6f}", "" if math.isnan(ci) else f"{ci:.6f}", n])
    (args.out / "harvest_table.tex").write_text(harvest_table_tex(groups))
    (args.out / "harvest_label2_table.tex").write_text(harvest_table_tex(groups, min_grade=2))
    (args.out / "efficiency_table.tex").write_text(efficiency_table_tex(groups))
    (args.out / "validity_table.tex").write_text(validity_table_tex(records))
    (args.out / "replay_table.tex").write_text(replay_table_tex(records))

    def graph_metric(fn):
        def value(r: RunRecord, k: int) -> float:
            grades = graph_grades(args.graphs_dir, r.graph)
            return float("nan") if grades is None else fn(r, k, grades)
        return value

    (args.out / "recall_table.tex").write_text(metric_table_tex(
        groups, graph_metric(lambda r, k, g: recall_at(r.labels, k, g[1] + g[2]))))
    if args.ndcg:
        (args.out / "ndcg_table.tex").write_text(metric_table_tex(
            groups, graph_metric(lambda r, k, g: ndcg_at(r.labels, k, g))))
    tests = wilcoxon(groups, args.test_k)
    (args.out / "wilcoxon_table.tex").write_text(wilcoxon_table_tex(tests, args.test_k))

    print(f"{len(live)} live runs read ({len(records) - len(live)} replays), {skipped} invalid excluded; wrote {args.out}/")
    for policy, runs in groups.items():
        mean, ci = mean_ci([harvest_at(r.labels, args.test_k) for r in runs])
        print(f"  {policy:<16} harvest@{args.test_k} {mean:.3f} +/- {ci:.3f}  (n={len(runs)})")
    print(f"\n  {'policy':<16} {'label2@30':>9} {'recall@30':>10} {'rel/call':>9} {'rel/1k tok':>11}  valid/invalid/early")
    validity = validity_counts(records)
    for policy, runs in groups.items():
        l2 = statistics.mean(harvest_at(r.labels, args.test_k, 2) for r in runs)
        rec = [graph_metric(lambda r, k, g: recall_at(r.labels, k, g[1] + g[2]))(r, args.test_k) for r in runs]
        rec = [v for v in rec if not math.isnan(v)]
        eff = [efficiency(r) for r in runs]
        per_call = [e[0] for e in eff if not math.isnan(e[0])]
        per_tok = [e[1] for e in eff if not math.isnan(e[1])]
        v = validity[policy]
        print(f"  {policy:<16} {l2:>9.3f} {statistics.mean(rec) if rec else float('nan'):>10.3f} "
              f"{statistics.mean(per_call) if per_call else float('nan'):>9.3f} "
              f"{statistics.mean(per_tok) if per_tok else float('nan'):>11.3f}  "
              f"{v['valid']}/{v['invalid']}/{v['early']}")
    for policy, c in replay_counts(records).items():
        print(f"  replay {policy}: {c['replays']} replayed, {c['misses']} cache misses in {c['with_misses']}")
    for t in tests:
        print(f"  cascade vs {t['policy']:<16} n={t['n']} p={t['p']:.4f}")


if __name__ == "__main__":
    main()
