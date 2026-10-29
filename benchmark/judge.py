"""The 0/1/2 relevance judge: one rubric prompt per batch of pages, validated and retried."""

import asyncio
from pathlib import Path
from typing import Any, Protocol

import aiohttp

from models.llm_context import LlmContext

from .label import EXCERPT_CHARS, MODEL, PROVIDER

RUBRIC = Path(__file__).with_name("rubric.md")
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 20
RETRYABLE_STATUSES = (429, 500, 502, 503)
VALID_LABELS = (0, 1, 2)

PROMPT = """You label web pages for a topical crawler benchmark, using this rubric.

{rubric}

Pages (title: first {n} characters):
{pages}

Answer with JSON only: {{"labels": {{"1": 0, "2": 1, ...}}}} \
with one integer 0, 1 or 2 per page number."""


class LlmSender(Protocol):
    async def send(self, context: LlmContext) -> dict[str, Any]: ...  # Any: provider JSON


def rubric_body() -> str:
    text = RUBRIC.read_text()
    return text[text.index("Target:") : text.index("## Judge output")].strip()


def retry_note(attempt: int) -> str:
    # A bad answer is cached under its prompt; a retry must change the prompt to reach the model.
    return f"\n(Attempt {attempt + 1}: answer every page number.)" if attempt else ""


def is_valid_label(value: object) -> bool:
    return isinstance(value, int) and value in VALID_LABELS


async def judge(llm: LlmSender, rows: list[dict[str, str]]) -> dict[str, int]:
    """Label each row 0, 1 or 2; retry with a changed prompt until every page has an answer."""
    pages = "\n".join(
        f"{i}. {r['title']}: {r['excerpt'][:EXCERPT_CHARS]}" for i, r in enumerate(rows, 1)
    )
    prompt = PROMPT.format(rubric=rubric_body(), n=EXCERPT_CHARS, pages=pages)
    for attempt in range(MAX_ATTEMPTS):
        try:
            result = await llm.send(LlmContext(PROVIDER, MODEL, prompt + retry_note(attempt)))
        except aiohttp.ClientResponseError as e:
            if e.status not in RETRYABLE_STATUSES:
                raise
            result = {}
        labels = result.get("labels", {})
        if all(is_valid_label(labels.get(str(i))) for i in range(1, len(rows) + 1)):
            return {r["id"]: labels[str(i)] for i, r in enumerate(rows, 1)}
        await asyncio.sleep(BACKOFF_SECONDS * (attempt + 1))
    raise RuntimeError("no usable answer")
