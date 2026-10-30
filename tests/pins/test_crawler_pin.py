"""Pin: the offline demo blueprint crawled through ``Crawler``, the composition root."""

from collections.abc import Callable, Iterable
from pathlib import Path

from pin_crawler import LLM_PROMPTS_PINNED, run_pin_crawler

PIN = "crawler"
# The demo blueprint's own budget is 40 pages; a small one keeps the pin to a few seconds.
PAGE_BUDGET = 5


async def test_crawler_matches_its_golden_files(
    golden: Callable[[str, str, Iterable[object]], None],
    tmp_path: Path,
) -> None:
    run = await run_pin_crawler(PAGE_BUDGET, tmp_path)

    assert run.fetched_total >= PAGE_BUDGET
    assert run.llm_calls_total >= LLM_PROMPTS_PINNED
    golden(PIN, "composition", run.composition)
    golden(PIN, "fetch_order", run.fetch_order)
    golden(PIN, "llm_requests", run.llm_requests)
