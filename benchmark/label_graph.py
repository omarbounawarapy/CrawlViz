"""Labels every page of a frozen graph 0/1/2 under the frozen rubric (benchmark/rubric.md).

Answers are cached (pilot_cache.jsonl) and each label is appended to a JSONL as it lands, so
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

from .graph import FrozenGraph
from .llm_cache import CachedLlm
from .pilot import judge  # same prompt and validation as the pilot
from .label import BATCH, EXCERPT_CHARS, TOKENS_PER_MINUTE

RUBRIC = Path(__file__).with_name("rubric.md")
LABELS = Path("benchmark/data/ball_labels.jsonl")
CACHE = Path("benchmark/data/pilot_cache.jsonl")


def rubric_sha() -> str:
    return hashlib.sha256(RUBRIC.read_bytes()).hexdigest()


def done() -> dict[str, int]:
    if not LABELS.exists():
        return {}
    return {d["page"]: d["label"] for d in map(json.loads, LABELS.read_text().splitlines())}


async def label(graph: FrozenGraph, keys: Path) -> None:
    got = done()
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
        with LABELS.open("a") as f:
            for n, v in result.items():
                f.write(json.dumps({"page": n, "label": v}, ensure_ascii=False) + "\n")
        if llm.misses > before:
            tokens = sum(len(r["excerpt"]) + len(r["title"]) for r in rows) / 3.5 + 1400
            await asyncio.sleep(60 * tokens / TOKENS_PER_MINUTE)
        print(f"\r{len(got) + s + len(batch)}/{len(graph.pages)}", end="", flush=True)
    print()
    await llm.inner.client.close()


def merge(graph: FrozenGraph, path: Path) -> None:
    got = done()
    missing = [n for n in graph.pages if n not in got]
    if missing:
        raise SystemExit(f"{len(missing)} pages unlabelled; run without --merge first")
    for n, v in got.items():
        graph.pages[n]["label"] = v
    data = json.loads(path.read_text())
    data["rubric_sha256"] = rubric_sha()
    data["rubric"] = RUBRIC.read_text()
    for n, v in got.items():
        data["pages"][n]["label"] = v
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
        merge(graph, args.graph)
    else:
        asyncio.run(label(graph, args.keys))


if __name__ == "__main__":
    main()
