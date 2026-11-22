"""Per-crawl cap on LLM calls, tokens and estimated cost, shared by every scoring worker.

A crawl that reaches a cap does not stop: the links that would have gone to
the LLM are scored on their NLP score alone, as the cascade already does for
high-confidence links. Calls are reserved before they are sent (`take`);
tokens and cost are known only after, so they are charged afterwards
(`charge`) and the calls already granted may go past a token or cost cap by
what they use. Scoring workers run on one event loop, so the counters need no lock.
"""

import logging

logger = logging.getLogger(__name__)


class CallBudget:
    """The crawl's LLM budget.

    Args:
        limit: Calls the crawl may make; None for no cap.
        max_tokens: Input and output tokens the crawl may use; None for no cap.
        max_cost_usd: Estimated dollars the crawl may spend; None for no cap.
            Calls without a price add nothing to the estimate.
    """

    def __init__(
        self,
        limit: int | None,
        *,
        max_tokens: int | None = None,
        max_cost_usd: float | None = None,
    ) -> None:
        for name, cap in (
            ("limit", limit),
            ("max_tokens", max_tokens),
            ("max_cost_usd", max_cost_usd),
        ):
            if cap is not None and cap < 0:
                raise ValueError(f"{name} must not be negative, not {cap}")
        self.limit = limit
        self.max_tokens = max_tokens
        self.max_cost_usd = max_cost_usd
        self.used = 0
        self.refused = 0
        self.tokens_used = 0
        self.cost_usd = 0.0
        self._warned = False

    def take(self, calls: int) -> int:
        """Reserve up to `calls` LLM calls; returns how many were granted."""
        if self._spend_cap_reached():
            granted = 0
        elif self.limit is None:
            granted = calls
        else:
            granted = max(0, min(calls, self.limit - self.used))
        self.used += granted
        self.refused += calls - granted
        if calls > granted and not self._warned:
            self._warned = True
            logger.warning(
                "LLM %s reached: remaining links are scored on NLP alone", self._reached_cap()
            )
        return granted

    def charge(self, input_tokens: int, output_tokens: int, cost_usd: float | None) -> None:
        """Count what one answered call used; `cost_usd` None when it has no price."""
        self.tokens_used += input_tokens + output_tokens
        if cost_usd is not None:
            self.cost_usd += cost_usd

    @property
    def exhausted(self) -> bool:
        calls_reached = self.limit is not None and self.used >= self.limit
        return calls_reached or self._spend_cap_reached()

    def _spend_cap_reached(self) -> bool:
        tokens_reached = self.max_tokens is not None and self.tokens_used >= self.max_tokens
        cost_reached = self.max_cost_usd is not None and self.cost_usd >= self.max_cost_usd
        return tokens_reached or cost_reached

    def _reached_cap(self) -> str:
        if self.max_tokens is not None and self.tokens_used >= self.max_tokens:
            return f"token budget of {self.max_tokens}"
        if self.max_cost_usd is not None and self.cost_usd >= self.max_cost_usd:
            return f"estimated cost budget of {self.max_cost_usd:g} USD"
        return f"call budget of {self.limit}"

    def snapshot(self) -> dict[str, int | bool | None]:
        return {
            "limit": self.limit,
            "used": self.used,
            "refused": self.refused,
            "exhausted": self.exhausted,
        }
