"""Labels every page of a frozen graph 0/1/2 under the frozen rubric (benchmark/rubric.md).

Answers are cached (pilot_cache.jsonl) and each label is appended to <graph>_labels.jsonl as it lands, so
a stopped run resumes where it left off. ``--merge`` writes the labels and the rubric hash
into the graph file.

    .venv/bin/python -m benchmark.label_graph --graph benchmark/data/ball.json
    .venv/bin/python -m benchmark.label_graph --graph benchmark/data/ball.json --merge
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path

import aiohttp

from infrastructure import KeyManager, LlmHandler

from .graph import FrozenGraph, page_key
from .llm_cache import CachedLlm
from .pilot import judge  # same prompt and validation as the pilot
from .label import BATCH, EXCERPT_CHARS, TOKENS_PER_MINUTE

RUBRIC = Path(__file__).with_name("rubric.md")
CACHE = Path("benchmark/data/pilot_cache.jsonl")


def rubric_sha() -> str:
    return hashlib.sha256(RUBRIC.read_bytes()).hexdigest()


def labels_path(graph_file: Path) -> Path:
    """Each graph has its own label log: <graph>_labels.jsonl next to it."""
    return graph_file.with_name(graph_file.stem + "_labels.jsonl")


def done(labels: Path) -> dict[str, int]:
    if not labels.exists():
        return {}
    return {page_key(d["page"]): d["label"] for d in map(json.loads, labels.read_text().splitlines())}


async def label(graph: FrozenGraph, keys: Path, labels: Path) -> None:
    got = done(labels)
    todo = [n for n in sorted(graph.pages) if n not in got]
    llm = CachedLlm(LlmHandler(KeyManager(keys_file=keys)), CACHE)
    for s in range(0, len(todo), BATCH):
        batch = todo[s : s + BATCH]
        rows = [{"id": n, "title": graph.pages[n]["title"], "excerpt": graph.pages[n]["text"][:EXCERPT_CHARS].replace("\n", " ")} for n in batch]
        before = llm.misses
        try:
            result = await judge(llm, rows)
        except (RuntimeError, aiohttp.ClientError) as e:
            print(f"\nbatch at {batch[0]} failed: {e!r}; waiting 60 s", flush=True)
            await asyncio.sleep(60)
            continue
        with labels.open("a") as f:
            for n, v in result.items():
                f.write(json.dumps({"page": n, "label": v}, ensure_ascii=False) + "\n")
        if llm.misses > before:
            tokens = sum(len(r["excerpt"]) + len(r["title"]) for r in rows) / 3.5 + 1400
            await asyncio.sleep(60 * tokens / TOKENS_PER_MINUTE)
        print(f"\r{len(got) + s + len(batch)}/{len(graph.pages)}", end="", flush=True)
    print()
    await llm.inner.client.close()


def merge(graph: FrozenGraph, path: Path, labels: Path) -> None:
    got = done(labels)
    missing = [n for n in graph.pages if n not in got]
    if missing:
        raise SystemExit(f"{len(missing)} pages unlabelled; run without --merge first")
    for n in graph.pages:
        graph.pages[n]["label"] = got[n]
        # Kept for files and tools that predate grading: true only for a direct target.
        graph.pages[n]["relevant"] = got[n] == 2
    # Written through the graph, so page names stay in their canonical form.
    graph.save(path)
    data = json.loads(path.read_text())
    data["rubric_sha256"] = rubric_sha()
    data["rubric"] = RUBRIC.read_text()
    path.write_text(json.dumps(data, ensure_ascii=False))
    counts = {k: list(got.values()).count(k) for k in (0, 1, 2)}
    print("merged", counts, "rubric", rubric_sha()[:12])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--graph", type=Path, required=True)
    ap.add_argument("--keys", type=Path, default=Path("keys.json"))
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()
    graph = FrozenGraph.load(args.graph)
    if args.merge:
        merge(graph, args.graph, labels_path(args.graph))
    else:
        asyncio.run(label(graph, args.keys, labels_path(args.graph)))


if __name__ == "__main__":
    main()
