"""Applies GRAPH_RULE.md: link distance to the target and radius-2 ball size per candidate seed.
Uses only the MediaWiki links API (titles, no page bodies)."""
import asyncio

import aiohttp

API = "https://fr.wikipedia.org/w/api.php"
UA = "crawlviz-benchmark/0.1 (https://github.com/omarbounawarapy; research benchmark)"
TARGET = "Institut supérieur d'informatique (Tunisie)"
CANDIDATES = ["Enseignement supérieur en Tunisie", "Liste des universités en Tunisie", "Tunisie"]


async def links_of(session, titles: list[str]) -> dict[str, set[str]]:
    out = {t: set() for t in titles}
    for i in range(0, len(titles), 50):
        batch = titles[i : i + 50]
        params = {"action": "query", "prop": "links", "titles": "|".join(batch), "pllimit": "max",
                  "plnamespace": "0", "format": "json", "redirects": "1"}
        while True:
            async with session.get(API, params=params) as r:
                data = await r.json()
            norm = {n["to"]: n["from"] for n in data.get("query", {}).get("normalized", [])}
            redir = {n["to"]: n["from"] for n in data.get("query", {}).get("redirects", [])}
            for page in data.get("query", {}).get("pages", {}).values():
                t = page["title"]
                src = norm.get(redir.get(t, t), redir.get(t, t))
                src = src if src in out else next((b for b in batch if b.replace("_", " ") == src), None)
                if src in out:
                    out[src] |= {link["title"] for link in page.get("links", [])}
            if "continue" not in data:
                break
            params.update(data["continue"])
            await asyncio.sleep(0.2)
        await asyncio.sleep(0.2)
    return out


async def probe(session, seed: str) -> tuple[int | None, int]:
    d1 = (await links_of(session, [seed]))[seed]
    d1_links = await links_of(session, sorted(d1))
    d2 = set().union(*d1_links.values()) - d1 - {seed}
    ball = {seed} | d1 | d2
    dist = 1 if TARGET in d1 else 2 if TARGET in d2 else None
    return dist, len(ball)


async def main():
    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as s:
        for seed in CANDIDATES:
            dist, size = await probe(s, seed)
            ok = dist == 2 and 3000 <= size <= 20000
            print(f"{seed!r}: target distance {dist}, radius-2 ball {size} pages -> {'QUALIFIES' if ok else 'rejected'}", flush=True)
            if ok:
                return


asyncio.run(main())
