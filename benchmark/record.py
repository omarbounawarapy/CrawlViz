"""Records a real site into a frozen graph.

Breadth-first from a seed, no scoring, so the recorded page set does not
depend on any policy under test. Raw pages are cached on disk, so a rerun
or a larger budget never refetches. Pages are saved with ``relevant: null``;
labels are added in a separate step.

    .venv/bin/python -m benchmark.record --seed 'Universit%C3%A9_de_Tunis_El_Manar' \\
        --pages 400 --out benchmark/data/isi.json
"""
import argparse
import asyncio
from collections import deque
from pathlib import Path
from urllib.parse import unquote, urldefrag

import aiohttp
from lxml import html as lhtml

from .graph import FrozenGraph

HOST = "https://fr.wikipedia.org"
USER_AGENT = "crawlviz-benchmark/0.1 (https://github.com/omarbounawarapy; research benchmark)"
TEXT_CHARS = 2000


def wiki_name(href: str) -> str | None:
    """Article name from an href, or None for anything that is not an article."""
    href = urldefrag(href)[0]
    if href.startswith(HOST):
        href = href[len(HOST):]
    if not href.startswith("/wiki/"):
        return None
    name = href[len("/wiki/"):]
    if not name or "/" in name or "?" in name or ":" in unquote(name):
        return None
    return name


BOILERPLATE = (
    "mw-editsection", "hatnote", "homonymie", "bandeau-article", "bandeau-container",
    "bandeau-portail", "bandeau-homonymie", "ambox", "navbox", "navbar", "noprint", "metadata",
)


def _drop(nodes) -> None:
    for node in nodes:
        if node.getparent() is not None:
            node.drop_tree()  # keeps the text that follows the node


def parse(name: str, raw: str) -> dict:
    root = lhtml.fromstring(raw)
    title = root.xpath("string(//h1[@id='firstHeading'])").strip() or unquote(name)
    canonical = root.xpath("string(//link[@rel='canonical']/@href)")
    body = root.xpath("//div[contains(@class, 'mw-parser-output')]")
    scope = body[0] if body else root
    _drop(scope.xpath(".//*[contains(@class, 'mw-editsection')]"))
    links, seen = [], set()
    for a in scope.xpath(".//a[@href]"):
        target = wiki_name(a.get("href"))
        if target and target != name and target not in seen:
            seen.add(target)
            links.append({"to": target, "anchor": a.text_content().strip()})
    # Text only after the links are taken: banners and hatnotes are noise for a
    # judge or a scorer, but a crawler would still follow their links.
    for cls in BOILERPLATE:
        _drop(scope.xpath(f".//*[contains(concat(' ', normalize-space(@class), ' '), ' {cls} ')]"))
    _drop(scope.xpath(".//sup[contains(@class, 'reference')]"))
    text = " ".join(" ".join(p.text_content().split()) for p in scope.xpath(".//p[normalize-space()]"))
    return {"title": title, "canonical": canonical, "text": text[:TEXT_CHARS], "links": links}


async def fetch(session, name: str, cache: Path, delay: float) -> str | None:
    path = cache / f"{name}.html"
    if path.exists():
        return path.read_text()
    await asyncio.sleep(delay)
    for attempt in range(3):
        try:
            async with session.get(f"{HOST}/wiki/{name}") as resp:
                if resp.status == 200:
                    raw = await resp.text()
                    path.write_text(raw)
                    return raw
                if resp.status == 404:
                    return None
                await asyncio.sleep(2 ** attempt)
        except aiohttp.ClientError:
            await asyncio.sleep(2 ** attempt)
    return None


async def record(seed: str, pages: int, cache: Path, delay: float, workers: int) -> FrozenGraph:
    cache.mkdir(parents=True, exist_ok=True)
    recorded: dict[str, dict] = {}
    queued = {seed}
    queue = deque([seed])
    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
        while queue and len(recorded) < pages:
            batch = [queue.popleft() for _ in range(min(workers, len(queue), pages - len(recorded)))]
            raws = await asyncio.gather(*(fetch(session, n, cache, delay) for n in batch))
            for name, raw in zip(batch, raws):
                if raw is None:
                    continue
                recorded[name] = parse(name, raw)
                for link in recorded[name]["links"]:
                    if link["to"] not in queued:
                        queued.add(link["to"])
                        queue.append(link["to"])
            print(f"\r{len(recorded)}/{pages}", end="", flush=True)
    print()
    # Close the graph: a link to a page that was never recorded would 404 in replay.
    for page in recorded.values():
        page["links"] = [link for link in page["links"] if link["to"] in recorded]
        page["relevant"] = None
    return FrozenGraph(seed=seed, pages=recorded)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", required=True, help="article name, percent-encoded as in the URL")
    ap.add_argument("--pages", type=int, default=400)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=Path("benchmark/data/raw"))
    ap.add_argument("--delay", type=float, default=0.5, help="seconds before each request")
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    graph = asyncio.run(record(args.seed, args.pages, args.cache, args.delay, args.workers))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    graph.save(args.out)
    links = sum(len(p["links"]) for p in graph.pages.values())
    print(f"{len(graph.pages)} pages, {links} links, saved to {args.out}")


if __name__ == "__main__":
    main()
