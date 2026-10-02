"""Records the radius-2 ball around a seed (GRAPH_RULE.md) into a frozen graph.

Pages are fetched with their HTML, parsed once, and appended to a JSONL
checkpoint (``--cache``), so a stopped run resumes and nothing is stored raw.
The ball is defined by link distance from the seed over what was fetched, not
by crawl order: every page at distance 0, 1 or 2 is fetched, and links from
distance-2 pages to pages outside the ball are dropped.

    .venv/bin/python -m benchmark.record_ball --seed 'Enseignement_sup%C3%A9rieur_en_Tunisie' \\
        --out benchmark/data/ball.json
"""
import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import quote, unquote

import aiohttp

from .graph import FrozenGraph
from .record import HOST, USER_AGENT, parse


def key(name: str) -> str:
    """One spelling per page: decoded, underscores, then percent-encoded."""
    return quote(unquote(name).replace(" ", "_"), safe="")


async def fetch_page(session, name: str, sem, retries: int = 4) -> dict | None:
    async with sem:
        for attempt in range(retries):
            try:
                async with session.get(f"{HOST}/wiki/{name}") as resp:
                    if resp.status == 200:
                        page = parse(name, await resp.text())
                        await asyncio.sleep(0.05)
                        return page
                    if resp.status == 404:
                        return None
                    wait = float(resp.headers.get("Retry-After", 2 ** attempt))
                    await asyncio.sleep(wait)
            except (aiohttp.ClientError, asyncio.TimeoutError):
                await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"gave up on {name}")


async def fetch_all(names: list[str], cache: dict, cache_path: Path, workers: int) -> None:
    todo = [n for n in names if n not in cache]
    sem = asyncio.Semaphore(workers)
    done = 0
    async with aiohttp.ClientSession(
        headers={"User-Agent": USER_AGENT}, timeout=aiohttp.ClientTimeout(total=60)
    ) as session:
        async def one(name):
            nonlocal done
            page = await fetch_page(session, name, sem)
            cache[name] = page
            with cache_path.open("a") as f:
                f.write(json.dumps({"name": name, "page": page}, ensure_ascii=False) + "\n")
            done += 1
            if done % 100 == 0:
                print(f"\\r  {done}/{len(todo)}", end="", flush=True)

        await asyncio.gather(*(one(n) for n in todo))
    if todo:
        print()


async def record(seed: str, cache_path: Path, workers: int) -> FrozenGraph:
    cache: dict[str, dict | None] = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            e = json.loads(line)
            cache[e["name"]] = e["page"]
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    def links_of(name):
        page = cache.get(name)
        return [link["to"] for link in page["links"]] if page else []

    print("distance 0 and 1")
    await fetch_all([seed], cache, cache_path, workers)
    d1 = sorted(set(links_of(seed)) - {seed})
    await fetch_all(d1, cache, cache_path, workers)
    print(f"distance 2 ({len(d1)} pages at distance 1)")
    d2 = sorted({t for n in d1 for t in links_of(n)} - set(d1) - {seed})
    await fetch_all(d2, cache, cache_path, workers)

    # Redirects: several link names can reach one article. The canonical URL names it.
    ball_names = [seed, *d1, *d2]
    canon: dict[str, str] = {}
    for n in ball_names:
        page = cache.get(n)
        if page:
            canon[n] = key(page["canonical"].rsplit("/wiki/", 1)[-1]) if "/wiki/" in page["canonical"] else key(n)
    members = set(canon.values())
    pages: dict[str, dict] = {}
    for n in ball_names:
        page = cache.get(n)
        if not page:
            continue
        k = canon[n]
        if k in pages:
            continue
        links, seen = [], set()
        for link in page["links"]:
            t = canon.get(link["to"], key(link["to"]))
            if t in members and t != k and t not in seen:
                seen.add(t)
                links.append({"to": t, "anchor": link["anchor"]})
        pages[k] = {"title": page["title"], "text": page["text"], "label": None, "links": links}
    return FrozenGraph(seed=canon[seed], pages=pages)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=Path("benchmark/data/ball_pages.jsonl"))
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    graph = asyncio.run(record(args.seed, args.cache, args.workers))
    graph.save(args.out)
    links = sum(len(p["links"]) for p in graph.pages.values())
    print(f"{len(graph.pages)} pages, {links} links, saved to {args.out}")


if __name__ == "__main__":
    main()
