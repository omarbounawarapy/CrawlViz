"""Labels a recorded graph with an LLM judge, once, offline.

The judge sees each page's title and the start of its text and answers
"is this page about the topic?". Answers are cached (``--cache``), so
relabelling an unchanged page is free. A seeded sample goes to a TSV for a
human to label too; ``--agreement`` compares the two, which is the only
evidence the metric measures what it should.

    .venv/bin/python -m benchmark.label --graph benchmark/data/isi.json \\
        --topic "institut superieur informatique ISI (tunisia / ariana)"
    .venv/bin/python -m benchmark.label --graph benchmark/data/isi.json --agreement
"""
import argparse
import asyncio
import csv
import random
import re
from pathlib import Path

import aiohttp

from infrastructure import KeyManager, LlmHandler
from models.llm_context import LlmContext

from .graph import FrozenGraph
from .llm_cache import CachedLlm

PROVIDER, MODEL = "groq", "qwen/qwen3.8-27b"  # a different family from the cascade's model (llama-3.3-70b was retired on Groq)
BATCH = 8
EXCERPT_CHARS = 450
TOKENS_PER_MINUTE = 5500  # Groq's cap on this key is 8000
SPOT_CHECK = 60

PROMPT = """You label web pages for a topical crawler benchmark.

Topic: {topic}

A page is RELEVANT only if it is about the topic itself: the institution or
thing named, or a closely related one of the same kind (same country and level),
its departments, programmes, or people directly tied to it. A page that merely
mentions the topic in passing, or is about a broad area (a country, a science,
a city), is NOT relevant.

Pages:
{pages}

Answer with JSON only: {{"labels": {{"1": true, "2": false, ...}}}} with one entry per page number."""


def excerpt(page: dict) -> str:
    return f'{page["title"]}: {page["text"][:EXCERPT_CHARS]}'.replace("\n", " ")


def make_prompt(topic: str, batch: list[tuple[str, dict]]) -> str:
    pages = "\n".join(f"{i}. {excerpt(page)}" for i, (_, page) in enumerate(batch, 1))
    return PROMPT.format(topic=topic, pages=pages)


async def judge(llm, topic: str, batch: list[tuple[str, dict]]) -> dict[str, bool]:
    prompt = make_prompt(topic, batch)
    for attempt in range(6):
        try:
            result = await llm.send(LlmContext(PROVIDER, MODEL, prompt + (f"\n(Attempt {attempt + 1}: answer every page number.)" if attempt else "")))
        except aiohttp.ClientResponseError as e:
            if e.status != 429:
                raise
            result = {}
        labels = result.get("labels", {}) if isinstance(result, dict) else {}
        if all(str(i) in labels for i in range(1, len(batch) + 1)):
            return {name: bool(labels[str(i)]) for i, (name, _) in enumerate(batch, 1)}
        await asyncio.sleep(20 * (attempt + 1))
    raise RuntimeError(f"no usable answer for batch starting at {batch[0][0]}")


async def label_graph(graph: FrozenGraph, cache: Path, keys: Path, limit: int | None) -> CachedLlm:
    llm = CachedLlm(LlmHandler(KeyManager(keys_file=keys)), cache)
    items = sorted(graph.pages.items())[:limit]
    for start in range(0, len(items), BATCH):
        batch = items[start : start + BATCH]
        before = llm.misses
        for name, label in (await judge(llm, graph.topic, batch)).items():
            graph.pages[name]["relevant"] = label
        if llm.misses > before:  # a real call: stay under the token cap
            prompt_tokens = len(make_prompt(graph.topic, batch)) / 3.5 + 120
            await asyncio.sleep(60 * prompt_tokens / TOKENS_PER_MINUTE)
        print(f"\r{min(start + BATCH, len(items))}/{len(items)}", end="", flush=True)
    print()
    await llm.inner.client.close()
    return llm


def write_spot_check(graph: FrozenGraph, path: Path) -> None:
    names = sorted(n for n, p in graph.pages.items() if p["relevant"] is not None)
    sample = random.Random("spot-check").sample(names, min(SPOT_CHECK, len(names)))
    with path.open("w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["page", "judge", "omar (1 relevant, 0 not)", "excerpt"])
        for name in sample:
            w.writerow([name, int(graph.pages[name]["relevant"]), "", excerpt(graph.pages[name])])


def agreement(graph: FrozenGraph, path: Path) -> None:
    rows = [r for r in csv.reader(path.open(), delimiter="\t")][1:]
    rows = [r for r in rows if r[2].strip() in ("0", "1")]
    if not rows:
        print("no human labels in", path)
        return
    judge_, human = [int(r[1]) for r in rows], [int(r[2]) for r in rows]
    both = sum(j and h for j, h in zip(judge_, human))
    print(f"{len(rows)} pages labelled by hand")
    print(f"agreement {sum(j == h for j, h in zip(judge_, human)) / len(rows):.0%}")
    print(f"judge relevant {sum(judge_)}, human relevant {sum(human)}, both {both}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--graph", type=Path, required=True)
    ap.add_argument("--topic", help="what relevant means; saved into the graph")
    ap.add_argument("--terms", help="comma-separated topic words for the lexical baseline")
    ap.add_argument("--cache", type=Path, default=Path("benchmark/data/judge_cache.jsonl"))
    ap.add_argument("--keys", type=Path, default=Path("keys.json"))
    ap.add_argument("--limit", type=int, help="label only the first N pages (a dry run)")
    ap.add_argument("--spot", type=Path, default=Path("benchmark/data/spotcheck.tsv"))
    ap.add_argument("--agreement", action="store_true", help="compare the judge with the filled TSV")
    args = ap.parse_args()

    graph = FrozenGraph.load(args.graph)
    if args.agreement:
        agreement(graph, args.spot)
        return
    if args.topic:
        graph.topic = args.topic
    if not graph.topic:
        ap.error("--topic is required the first time")
    if args.terms:
        graph.terms = [t.strip().lower() for t in args.terms.split(",") if t.strip()]
    elif not graph.terms:
        graph.terms = sorted({w for w in re.findall(r"\w+", graph.topic.lower()) if len(w) > 3})
    llm = asyncio.run(label_graph(graph, args.cache, args.keys, args.limit))
    graph.save(args.graph)
    write_spot_check(graph, args.spot)
    labelled = [p["relevant"] for p in graph.pages.values() if p["relevant"] is not None]
    print(f"{sum(labelled)} relevant of {len(labelled)} labelled ({llm.hits} cached, {llm.misses} calls)")
    print(f"spot check written to {args.spot}")


if __name__ == "__main__":
    main()
