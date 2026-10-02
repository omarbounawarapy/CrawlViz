"""Pilot: the 0/1/2 judge against Omar's hand labels on the 30-page sample.

    .venv/bin/python -m benchmark.pilot
"""
import asyncio
import csv
import sys
from pathlib import Path

import aiohttp

from infrastructure import KeyManager, LlmHandler
from models.llm_context import LlmContext

from .label import BATCH, EXCERPT_CHARS, MODEL, PROVIDER
from .llm_cache import CachedLlm

RUBRIC = Path(__file__).with_name("rubric.md")
TSV = Path(sys.argv[1] if len(sys.argv) > 1 else "benchmark/data/pilot30.tsv")
CACHE = Path("benchmark/data/pilot_cache.jsonl")

PROMPT = """You label web pages for a topical crawler benchmark, using this rubric.

{rubric}

Pages (title: first {n} characters):
{pages}

Answer with JSON only: {{"labels": {{"1": 0, "2": 1, ...}}}} with one integer 0, 1 or 2 per page number."""


def rubric_body() -> str:
    text = RUBRIC.read_text()
    return text[text.index("Target:") : text.index("## Judge output")].strip()


def retry_note(attempt: int) -> str:
    # A bad answer is cached under its prompt; a retry must change the prompt to reach the model.
    return f"\n(Attempt {attempt + 1}: answer every page number.)" if attempt else ""


async def judge(llm, rows: list[dict]) -> dict[str, int]:
    pages = "\n".join(f"{i}. {r['title']}: {r['excerpt'][:EXCERPT_CHARS]}" for i, r in enumerate(rows, 1))
    prompt = PROMPT.format(rubric=rubric_body(), n=EXCERPT_CHARS, pages=pages)
    for attempt in range(4):
        try:
            result = await llm.send(LlmContext(PROVIDER, MODEL, prompt + retry_note(attempt)))
        except aiohttp.ClientResponseError as e:
            if e.status not in (429, 500, 502, 503):
                raise
            result = {}
        labels = result.get("labels", {}) if isinstance(result, dict) else {}
        if all(isinstance(labels.get(str(i)), int) and labels[str(i)] in (0, 1, 2) for i in range(1, len(rows) + 1)):
            return {r["id"]: labels[str(i)] for i, r in enumerate(rows, 1)}
        await asyncio.sleep(20 * (attempt + 1))
    raise RuntimeError("no usable answer")


async def main() -> None:
    rows = list(csv.DictReader(TSV.open(), delimiter="\t"))
    llm = CachedLlm(LlmHandler(KeyManager(keys_file=Path("keys.json"))), CACHE)
    got: dict[str, int] = {}
    for s in range(0, len(rows), BATCH):
        got.update(await judge(llm, rows[s : s + BATCH]))
        await asyncio.sleep(25)
    await llm.inner.client.close()
    human = {r["id"]: int(r["human_label"]) for r in rows}
    agree = sum(got[i] == human[i] for i in human)
    print(f"agreement {agree}/{len(rows)}")
    for r in rows:
        if got[r["id"]] != human[r["id"]]:
            print(f"DISAGREE {r['id']}: human {human[r['id']]} judge {got[r['id']]}  {r['title']}")
    print("judge counts", {k: list(got.values()).count(k) for k in (0, 1, 2)})


if __name__ == "__main__":
    asyncio.run(main())
