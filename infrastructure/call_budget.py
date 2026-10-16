"""Per-crawl cap on LLM calls, shared by every scoring worker of one crawl.

A crawl that reaches its cap does not stop: the links that would have gone to
the LLM are scored on their NLP score alone, as the cascade already does for
high-confidence links. Scoring workers run on one event loop, so the counter
needs no lock.
"""

import logging

logger = logging.getLogger(__name__)


class CallBudget:
    def __init__(self, limit: int | None):
        self.limit = limit
        self.used = 0
        self.refused = 0
        self._warned = False

    def take(self, calls: int) -> int:
        """Reserve up to `calls` LLM calls; returns how many were granted."""
        if self.limit is None:
            self.used += calls
            return calls
        granted = max(0, min(calls, self.limit - self.used))
        self.used += granted
        self.refused += calls - granted
        if calls > granted and not self._warned:
            self._warned = True
            logger.warning(
                "LLM call budget of %d reached: remaining links are scored on NLP alone",
                self.limit,
            )
        return granted

    @property
    def exhausted(self) -> bool:
        return self.limit is not None and self.used >= self.limit

    def snapshot(self) -> dict:
        return {"limit": self.limit, "used": self.used, "refused": self.refused,
                "exhausted": self.exhausted}
