"""python -m benchmark.analyze [--results DIR] [--out DIR] [--k 100] [--test-k 30]

Reads the per-run JSON files (benchmark.results) and writes, to ``--out``:

Pages that share a title are one article under several names (redirects):
with ``--graphs-dir`` each title counts once, at its first visit, before
harvest@k is computed.

* ``curves.csv``: harvest@k for k = 1..K, per policy: mean and 95% CI
* ``harvest_table.tex``: harvest at chosen k, mean +/- 95% CI, per policy
* ``wilcoxon_table.tex``: paired Wilcoxon signed-rank test of the cascade
  against every other policy on harvest@``--test-k``

Invalid runs are excluded. Runs are paired on (graph, repeat).
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


def harvest_at(labels: list[int], k: int) -> float:
    head = labels[:k]
    return sum(1 for v in head if v >= 1) / len(head) if head else 0.0


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
        if r.valid:
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


def harvest_table_tex(groups: dict[str, list[RunRecord]], ks=TABLE_KS) -> str:
    head = " & ".join(f"@{k}" for k in ks)
    lines = [r"\begin{tabular}{l" + "c" * len(ks) + "r}", r"\toprule",
             f"Policy & {head} & runs \\\\", r"\midrule"]
    for policy, runs in groups.items():
        cells = []
        for k in ks:
            mean, ci = mean_ci([harvest_at(r.labels, k) for r in runs])
            cells.append(f"{mean:.3f}" + ("" if math.isnan(ci) else f" $\\pm$ {ci:.3f}"))
        lines.append(f"{_tex(policy)} & " + " & ".join(cells) + f" & {len(runs)} \\\\")
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
    args = ap.parse_args()

    records = load_records(args.results)
    if not args.no_dedupe:
        records = dedupe_records(records, args.graphs_dir)
    groups = by_policy(records)
    if not groups:
        raise SystemExit(f"no valid runs in {args.results}")
    skipped = len(records) - sum(len(v) for v in groups.values())
    args.out.mkdir(parents=True, exist_ok=True)

    with (args.out / "curves.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["policy", "k", "mean", "ci95", "runs"])
        for policy, k, mean, ci, n in curves(groups, args.k):
            w.writerow([policy, k, f"{mean:.6f}", "" if math.isnan(ci) else f"{ci:.6f}", n])
    (args.out / "harvest_table.tex").write_text(harvest_table_tex(groups))
    tests = wilcoxon(groups, args.test_k)
    (args.out / "wilcoxon_table.tex").write_text(wilcoxon_table_tex(tests, args.test_k))

    print(f"{len(records)} runs read, {skipped} invalid excluded; wrote {args.out}/")
    for policy, runs in groups.items():
        mean, ci = mean_ci([harvest_at(r.labels, args.test_k) for r in runs])
        print(f"  {policy:<16} harvest@{args.test_k} {mean:.3f} +/- {ci:.3f}  (n={len(runs)})")
    for t in tests:
        print(f"  cascade vs {t['policy']:<16} n={t['n']} p={t['p']:.4f}")


if __name__ == "__main__":
    main()
