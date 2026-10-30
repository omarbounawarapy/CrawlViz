"""The seed-centred subgraph of a frozen graph, as the crawl graph view draws it."""

from collections import deque
from typing import Any

from benchmark.graph import FrozenGraph


def _breadth_first_tree(graph: FrozenGraph) -> tuple[dict[str, int], dict[str, str | None]]:
    """Depth and parent of every page reachable from the seed."""
    depth: dict[str, int] = {graph.seed: 0}
    parent: dict[str, str | None] = {graph.seed: None}
    queue = deque([graph.seed])
    while queue:
        n = queue.popleft()
        for link in graph.pages[n]["links"]:
            t = link["to"]
            if t in graph.pages and t not in depth:
                depth[t], parent[t] = depth[n] + 1, n
                queue.append(t)
    return depth, parent


def seed_subgraph(graph: FrozenGraph, name: str, max_depth: int, limit: int) -> dict[str, Any]:
    """Seed-centred subgraph as a breadth-first spanning tree (what the crawl graph view draws).

    Pages up to ``max_depth``, relevant pages first. ``parent`` is the page each
    one was first reached from; links that are not tree edges are counted in
    ``cross_links`` and not drawn.
    """
    depth, parent = _breadth_first_tree(graph)
    ranked = sorted(
        (n for n, d in depth.items() if d <= max_depth),
        key=lambda n: (-graph.label(n), depth[n], n),
    )
    keep = set(ranked[:limit])
    # A kept page needs its chain of ancestors, or the tree falls apart.
    for n in list(keep):
        a = parent[n]
        while a is not None and a not in keep:
            keep.add(a)
            a = parent[a]
    nodes = [
        {
            "id": n,
            "parent": parent[n],
            "title": graph.pages[n].get("title") or n,
            "label": graph.label(n),
            "depth": depth[n],
            "out": len(graph.pages[n]["links"]),
        }
        for n in sorted(keep, key=lambda n: (depth[n], n))
    ]
    tree = sum(1 for n in keep if parent[n] is not None)
    all_links = sum(1 for n in keep for link in graph.pages[n]["links"] if link["to"] in keep)
    return {
        "name": name,
        "seed": graph.seed,
        "topic": graph.topic,
        "total": len(graph.pages),
        "shown": len(nodes),
        "cross_links": all_links - tree,
        "nodes": nodes,
    }
