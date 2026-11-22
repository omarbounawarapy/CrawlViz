"""The LLM subsystem's entry on the crawl's status board (ADR 8).

``llm_facts`` and ``llm_state`` are pure: the facts come from the call totals and the call
budget, the state from how the last calls ended. ``LlmStatusTracker`` keeps what they need
between calls (calls in flight, failures in a row, the last provider and model) and reports
through a ``StatusReporter``, so the LLM layer never imports the board (ADR 4).

States, first match wins:

* ``failed`` / ``keys_missing``: the provider rejected the key (HTTP 401 or 403) and no
  other key was left to try.
* ``waiting`` / ``budget_exhausted``: a call, token or cost cap is reached; the links
  that would have gone to the LLM are scored on NLP alone.
* ``ready``: no call has failed yet, or the last call got an answer.
* ``waiting`` / ``rate_limited``: the last call ended on HTTP 429.
* ``failed`` / ``provider_error``: ``FAILURES_TO_REPORT_FAILED`` calls in a row failed.
* ``waiting`` / ``provider_error``: the last call failed, but fewer in a row; the crawl
  reschedules the page, so the LLM may still answer.

While a call waits to retry a 429 or 5xx answer, the entry is ``waiting`` with the retry
time. A report is a synchronous write to memory, O(1) in the size of the crawl (PERF-3).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from crawlviz.contracts import LlmFacts, SubsystemState
from crawlviz.events import StatusReporter

from .call_budget import CallBudget
from .call_recorder import LlmCallTotals
from .provider_statuses import REJECTED_KEY_STATUSES, TOO_MANY_REQUESTS
from .types import FAILED_OUTCOMES, CallOutcome, LlmCallRecord

SUBSYSTEM: Final = "llm"
# Reason codes from the LLM subsystem's closed list (crawlviz.contracts).
KEYS_MISSING: Final = "keys_missing"
RATE_LIMITED: Final = "rate_limited"
BUDGET_EXHAUSTED: Final = "budget_exhausted"
PROVIDER_ERROR: Final = "provider_error"

# Calls in a row that end without an answer before the LLM counts as failed, not waiting.
FAILURES_TO_REPORT_FAILED: Final = 3


@dataclass(frozen=True)
class LlmState:
    """The board state and reason code for the LLM subsystem."""

    state: SubsystemState
    reason: str | None = None


@dataclass(frozen=True)
class RecentCalls:
    """How the latest calls ended: what the state depends on beyond the budget.

    Attributes:
        last_outcome: How the last finished call ended; None before the first one.
        failures_in_a_row: Calls without an answer since the last one that had one.
        last_http_status: The provider's status for the last failed call, if it sent one.
    """

    last_outcome: CallOutcome | None = None
    failures_in_a_row: int = 0
    last_http_status: int | None = None

    def after(self, outcome: CallOutcome, http_status: int | None) -> "RecentCalls":
        """These calls followed by one more that ended with ``outcome``."""
        if outcome not in FAILED_OUTCOMES:
            return RecentCalls(last_outcome=outcome)
        return RecentCalls(outcome, self.failures_in_a_row + 1, http_status)


def llm_facts(
    totals: LlmCallTotals,
    budget: CallBudget | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
    in_flight: int = 0,
) -> LlmFacts:
    """The board facts for the crawl's LLM use so far.

    The call cap and the refused calls come from ``budget`` when there is one, since the
    budget counts the calls the score stage refused; without one, from ``totals``.
    """
    budget_calls = totals.budget_calls if budget is None else budget.limit
    return LlmFacts(
        provider=provider,
        model=model,
        calls=totals.calls,
        budget_calls=budget_calls,
        calls_refused=0 if budget is None else budget.refused,
        cache_hits=totals.cache_hits,
        failed_calls=totals.failed_calls,
        input_tokens=totals.input_tokens,
        output_tokens=totals.output_tokens,
        estimated_cost_usd=totals.estimated_cost_usd,
        in_flight=in_flight,
        outcomes={outcome.value: count for outcome, count in totals.outcomes.items()},
    )


def llm_state(recent: RecentCalls, *, budget_exhausted: bool = False) -> LlmState:
    """The board state for ``recent`` calls; see the module docstring for the rules."""
    failed_last = recent.last_outcome in FAILED_OUTCOMES
    if failed_last and recent.last_http_status in REJECTED_KEY_STATUSES:
        return LlmState("failed", KEYS_MISSING)
    if budget_exhausted:
        return LlmState("waiting", BUDGET_EXHAUSTED)
    if not failed_last:
        return LlmState("ready")
    if recent.last_http_status == TOO_MANY_REQUESTS:
        return LlmState("waiting", RATE_LIMITED)
    if recent.failures_in_a_row >= FAILURES_TO_REPORT_FAILED:
        return LlmState("failed", PROVIDER_ERROR)
    return LlmState("waiting", PROVIDER_ERROR)


class LlmStatusTracker:
    """Reports the LLM subsystem's state each time a call starts, waits or ends.

    Args:
        reporter: Where the reports go, the crawl's status board or a null reporter.
        budget: The crawl's call budget, for the cap, the refused calls and exhaustion.
        clock: Unix seconds, for the retry time of a waiting call; tests pass a fake.

    One tracker serves one crawl. Scoring workers share one event loop, so the counters
    need no lock.
    """

    def __init__(
        self,
        reporter: StatusReporter,
        *,
        budget: CallBudget | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.reporter = reporter
        self.budget = budget
        self._clock = clock
        self._totals = LlmCallTotals()
        self._recent = RecentCalls()
        self._in_flight = 0
        self._provider: str | None = None
        self._model: str | None = None

    @property
    def in_flight(self) -> int:
        return self._in_flight

    def call_started(self, provider: str, model: str) -> None:
        """A call is about to be sent to ``provider`` for ``model``."""
        self._in_flight += 1
        self._provider, self._model = provider, model
        self.refresh()

    def call_retrying(self, http_status: int, delay_seconds: float) -> None:
        """A call got a transient ``http_status`` and is retried in ``delay_seconds``."""
        reason = RATE_LIMITED if http_status == TOO_MANY_REQUESTS else PROVIDER_ERROR
        self._report(LlmState("waiting", reason), retry_at=self._clock() + delay_seconds)

    def call_finished(
        self, record: LlmCallRecord, totals: LlmCallTotals, http_status: int | None = None
    ) -> None:
        """A call ended as ``record`` says; ``totals`` already count it.

        ``http_status`` is the provider's status when the call failed on one.
        """
        self._in_flight = max(0, self._in_flight - 1)
        self._provider, self._model = record.provider, record.model
        self._totals = totals
        self._recent = self._recent.after(record.outcome, http_status)
        self.refresh()

    def refresh(self) -> None:
        """Report the state as it is now, for example after the budget refused calls."""
        exhausted = self.budget is not None and self.budget.exhausted
        self._report(llm_state(self._recent, budget_exhausted=exhausted))

    def _report(self, state: LlmState, *, retry_at: float | None = None) -> None:
        facts = llm_facts(
            self._totals,
            self.budget,
            provider=self._provider,
            model=self._model,
            in_flight=self._in_flight,
        )
        self.reporter.report(SUBSYSTEM, state.state, state.reason, facts, retry_at=retry_at)
