"""Records every LLM call: running totals for the crawl and `llm_calls.jsonl` lines.

The totals feed the live cost figures (R-COST-LIVE); the file feeds the "Why"
tab (R-WHY) through the runs API (ADR 12). The rendered prompt and the raw
reply hold page text, so they are written only when `store_text` is set.
"""

import asyncio
import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .cost_table import CostTable
from .types import CallOutcome, LlmCallRecord, TokenUsage

logger = logging.getLogger(__name__)

LLM_CALLS_FILE_NAME = "llm_calls.jsonl"
_FAILED_OUTCOMES = frozenset(
    {
        CallOutcome.INVALID_OUTPUT,
        CallOutcome.HTTP_ERROR,
        CallOutcome.NETWORK_ERROR,
        CallOutcome.BAD_RESPONSE,
    }
)


class LlmCallTotals(BaseModel):
    """What a crawl's LLM calls have used so far.

    Attributes:
        calls: Calls that reached the provider; cache hits are not counted.
        cache_hits: Answers served from the cache.
        failed_calls: Calls with no valid answer, cache hits included.
        input_tokens, output_tokens: Tokens the provider used; cache hits add none.
        repaired_calls: Calls whose answer passed only after the repair attempt.
        estimated_cost_usd: Sum over calls with a known price; None while none has one.
        calls_without_price: Calls left out of the estimate for want of a price.
        budget_calls: The crawl's call cap; None for no cap.
        remaining_calls: Calls left under the cap; None for no cap.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    calls: int = Field(default=0, ge=0)
    cache_hits: int = Field(default=0, ge=0)
    failed_calls: int = Field(default=0, ge=0)
    repaired_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float | None = None
    calls_without_price: int = Field(default=0, ge=0)
    budget_calls: int | None = None
    remaining_calls: int | None = None


class LlmCallRecorder:
    """Prices each call record, adds it to the totals and appends it to the file.

    Args:
        path: The `llm_calls.jsonl` file, or None to keep totals only.
        cost_table: Prices for the estimate; None leaves every cost unknown.
        budget_calls: The crawl's call cap, for `remaining_calls`.
        store_text: Keep the rendered prompt and raw reply in the file.
    """

    def __init__(
        self,
        path: Path | None,
        *,
        cost_table: CostTable | None = None,
        budget_calls: int | None = None,
        store_text: bool = False,
    ) -> None:
        self.path = path
        self.cost_table = CostTable() if cost_table is None else cost_table
        self.store_text = store_text
        self._totals = LlmCallTotals(budget_calls=budget_calls, remaining_calls=budget_calls)
        self._write_lock = asyncio.Lock()

    @property
    def totals(self) -> LlmCallTotals:
        return self._totals

    def price(self, record: LlmCallRecord) -> LlmCallRecord:
        """`record` with its estimated cost filled in when it has none."""
        if record.cost_usd is not None:
            return record
        if record.cache_hit:
            return record.model_copy(update={"cost_usd": 0.0})
        usage = TokenUsage(input_tokens=record.input_tokens, output_tokens=record.output_tokens)
        cost = self.cost_table.estimate_cost_usd(record.provider, record.model, usage)
        return record.model_copy(update={"cost_usd": cost})

    async def record(self, record: LlmCallRecord) -> LlmCallRecord:
        """Price `record`, count it and append it to the file; returns the priced record.

        Raises:
            OSError: If the file cannot be written; the totals still count the call.
        """
        priced = self.price(record)
        self._totals = _add(self._totals, priced)
        if self.path is not None:
            stored = priced if self.store_text else _without_text(priced)
            await self._append(self.path, stored.model_dump_json() + "\n")
        return priced

    async def _append(self, path: Path, line: str) -> None:
        async with self._write_lock:  # keeps lines whole and in call order
            try:
                await asyncio.to_thread(_append_line, path, line)
            except OSError:
                logger.exception("Could not append an LLM call record to %s", path)
                raise


def _add(totals: LlmCallTotals, record: LlmCallRecord) -> LlmCallTotals:
    # A cache hit spends no call and no tokens; its record keeps the original counts.
    spent = 0 if record.cache_hit else 1
    calls = totals.calls + spent
    cost = totals.estimated_cost_usd
    if record.cost_usd is not None:
        cost = (cost or 0.0) + record.cost_usd
    remaining = None if totals.budget_calls is None else max(0, totals.budget_calls - calls)
    return totals.model_copy(
        update={
            "calls": calls,
            "cache_hits": totals.cache_hits + int(record.cache_hit),
            "failed_calls": totals.failed_calls + int(record.outcome in _FAILED_OUTCOMES),
            "repaired_calls": totals.repaired_calls + int(record.outcome is CallOutcome.REPAIRED),
            "input_tokens": totals.input_tokens + spent * record.input_tokens,
            "output_tokens": totals.output_tokens + spent * record.output_tokens,
            "estimated_cost_usd": cost,
            "calls_without_price": totals.calls_without_price + int(record.cost_usd is None),
            "remaining_calls": remaining,
        }
    )


def _without_text(record: LlmCallRecord) -> LlmCallRecord:
    return record.model_copy(update={"rendered_prompt": None, "raw_reply": None})


def _append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(line)
