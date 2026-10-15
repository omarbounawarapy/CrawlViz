"""Descriptive statistics of a frozen graph, for the paper's dataset table.

    .venv/bin/python -m benchmark.graph_stats --graph benchmark/data/ball.json [--tex FILE]
"""
import argparse
import statistics
from collections import Counter, deque
from pathlib import Path

from .graph import FrozenGraph


def depths(graph: FrozenGraph) -> dict[str, int]:
    """Breadth-first distance from the seed, for the pages reachable from it."""
    out = {graph.seed: 0}
    queue = deque([graph.seed])
    while queue:
        name = queue.popleft()
        for link in graph.pages[name]["links"]:
            if link["to"] in graph.pages and link["to"] not in out:
                out[link["to"]] = out[name] + 1
                queue.append(link["to"])
    return out


def stats(graph: FrozenGraph) -> dict:
    degrees = [len(p["links"]) for p in graph.pages.values()]
    absent = sum(1 for p in graph.pages.values() for l in p["links"] if l["to"] not in graph.pages)
    depth = depths(graph)
    labels = {n: graph.label(n) for n in graph.pages}
    per_depth: dict[int, dict[str, int]] = {}
    for name, d in depth.items():
        row = per_depth.setdefault(d, {"pages": 0, "label1": 0, "label2": 0})
        row["pages"] += 1
        if labels[name] == 1:
            row["label1"] += 1
        elif labels[name] == 2:
            row["label2"] += 1
    return {
        "pages": len(graph.pages),
        "edges": sum(degrees),
        "out_degree": {
            "mean": statistics.mean(degrees) if degrees else 0.0,
            "median": statistics.median(degrees) if degrees else 0.0,
            "max": max(degrees, default=0),
        },
        "absent_links": absent,
        "reachable": len(depth),
        "depth_histogram": dict(sorted(Counter(depth.values()).items())),
        "labels": {g: sum(1 for v in labels.values() if v == g) for g in (0, 1, 2)},
        "relevant_per_depth": dict(sorted(per_depth.items())),
        "relevant_unreachable": sum(1 for n, v in labels.items() if v >= 1 and n not in depth),
    }


def to_text(s: dict) -> str:
    d = s["out_degree"]
    lines = [
        f"pages                 {s['pages']}",
        f"edges                 {s['edges']}",
        f"out-degree            mean {d['mean']:.1f}  median {d['median']:g}  max {d['max']}",
        f"links to absent pages {s['absent_links']}",
        f"reachable from seed   {s['reachable']}",
        f"labels                0: {s['labels'][0]}  1: {s['labels'][1]}  2: {s['labels'][2]}",
        f"relevant, unreachable {s['relevant_unreachable']}",
        "",
        f"{'depth':>5}{'pages':>9}{'label 1':>9}{'label 2':>9}{'relevant':>10}",
    ]
    for depth, row in s["relevant_per_depth"].items():
        lines.append(f"{depth:>5}{row['pages']:>9}{row['label1']:>9}{row['label2']:>9}{row['label1'] + row['label2']:>10}")
    return "\n".join(lines)


def to_tex(s: dict, name: str = "") -> str:
    d = s["out_degree"]
    rows = [
        ("Pages", f"{s['pages']:,}"),
        ("Edges", f"{s['edges']:,}"),
        ("Out-degree mean / median / max", f"{d['mean']:.1f} / {d['median']:g} / {d['max']}"),
        ("Links to absent pages", f"{s['absent_links']:,}"),
        ("Reachable from seed", f"{s['reachable']:,}"),
        ("Label 0 / 1 / 2", f"{s['labels'][0]:,} / {s['labels'][1]:,} / {s['labels'][2]:,}"),
        ("Maximum depth", str(max(s["depth_histogram"], default=0))),
    ]
    lines = [r"\begin{tabular}{lr}", r"\toprule", r"Statistic & Value \\", r"\midrule"]
    lines += [f"{k} & {v} \\\\" for k, v in rows]
    lines += [r"\bottomrule", r"\end{tabular}", "", r"\begin{tabular}{rrrrr}", r"\toprule",
              r"Depth & Pages & Label 1 & Label 2 & Relevant \\", r"\midrule"]
    for depth, row in s["relevant_per_depth"].items():
        lines.append(f"{depth} & {row['pages']:,} & {row['label1']:,} & {row['label2']:,} & "
                     f"{row['label1'] + row['label2']:,} \\\\")
    return "\n".join(lines + [r"\bottomrule", r"\end{tabular}", ""])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--graph", type=Path, required=True)
    ap.add_argument("--tex", type=Path, help="also write the LaTeX tables to this file")
    args = ap.parse_args()
    s = stats(FrozenGraph.load(args.graph))
    print(to_text(s))
    tex = to_tex(s)
    print("\n" + tex)
    if args.tex:
        args.tex.write_text(tex)


if __name__ == "__main__":
    main()
