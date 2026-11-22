"""The LLM entry on the status board: facts from the totals and budget, state from the calls."""

from datetime import UTC, datetime

import pytest

from crawlviz.contracts import LlmFacts, LlmStatus, make_report
from crawlviz.llm import (
    CallBudget,
    CallOutcome,
    LlmCallRecord,
    LlmCallTotals,
    LlmState,
    LlmStatusTracker,
    RecentCalls,
    llm_facts,
    llm_state,
)
from crawlviz.llm.llm_status import FAILURES_TO_REPORT_FAILED
from crawlviz.telemetry import StatusBoard

NOW = 1_000.0
STARTED = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
TOTALS = LlmCallTotals(
    calls=5,
    cache_hits=2,
    failed_calls=1,
    input_tokens=1_200,
    output_tokens=300,
    estimated_cost_usd=0.25,
    budget_calls=10,
    remaining_calls=5,
    outcomes={**dict.fromkeys(CallOutcome, 0), CallOutcome.OK: 6, CallOutcome.TIMEOUT: 1},
)


def record(outcome: CallOutcome = CallOutcome.OK) -> LlmCallRecord:
    return LlmCallRecord(
        started_at=STARTED,
        provider="openai",
        model="model-x",
        latency_ms=10.0,
        attempts=1,
        outcome=outcome,
    )


def test_facts_carry_the_totals_and_the_budget() -> None:
    budget = CallBudget(8)
    budget.take(9)

    facts = llm_facts(TOTALS, budget, provider="openai", model="model-x", in_flight=2)

    assert facts == LlmFacts(
        provider="openai",
        model="model-x",
        calls=5,
        budget_calls=8,
        calls_refused=1,
        cache_hits=2,
        failed_calls=1,
        input_tokens=1_200,
        output_tokens=300,
        estimated_cost_usd=0.25,
        in_flight=2,
        outcomes={**{outcome.value: 0 for outcome in CallOutcome}, "ok": 6, "timeout": 1},
    )


def test_without_a_budget_the_cap_comes_from_the_totals() -> None:
    facts = llm_facts(TOTALS)

    assert facts.budget_calls == 10
    assert facts.calls_refused == 0
    assert facts.provider is None


def test_facts_before_any_call_are_zero_with_every_outcome_listed() -> None:
    facts = llm_facts(LlmCallTotals())

    assert facts.calls == 0
    assert facts.estimated_cost_usd is None
    assert set(facts.outcomes) == {outcome.value for outcome in CallOutcome}


def recent(*outcomes: tuple[CallOutcome, int | None]) -> RecentCalls:
    calls = RecentCalls()
    for outcome, status in outcomes:
        calls = calls.after(outcome, status)
    return calls


FAILED = (CallOutcome.HTTP_ERROR, 500)
FAILED_IN_A_ROW = recent(*[FAILED] * FAILURES_TO_REPORT_FAILED)


@pytest.mark.parametrize(
    ("calls", "exhausted", "expected"),
    [
        (recent(), False, LlmState("ready")),
        (recent(FAILED, (CallOutcome.OK, None)), False, LlmState("ready")),
        (recent((CallOutcome.REPAIRED, None)), False, LlmState("ready")),
        (recent((CallOutcome.HTTP_ERROR, 429)), False, LlmState("waiting", "rate_limited")),
        (recent((CallOutcome.HTTP_ERROR, 401)), False, LlmState("failed", "keys_missing")),
        (recent((CallOutcome.HTTP_ERROR, 403)), True, LlmState("failed", "keys_missing")),
        (recent(FAILED), False, LlmState("waiting", "provider_error")),
        (recent((CallOutcome.TIMEOUT, None)), False, LlmState("waiting", "provider_error")),
        (FAILED_IN_A_ROW, False, LlmState("failed", "provider_error")),
        (recent(), True, LlmState("waiting", "budget_exhausted")),
        (recent(FAILED), True, LlmState("waiting", "budget_exhausted")),
    ],
)
def test_state_follows_the_latest_calls(
    calls: RecentCalls, exhausted: bool, expected: LlmState
) -> None:
    assert llm_state(calls, budget_exhausted=exhausted) == expected


def test_a_call_with_an_answer_resets_the_failures_in_a_row() -> None:
    calls = recent(FAILED, FAILED, (CallOutcome.OK, None), FAILED)

    assert calls.failures_in_a_row == 1


@pytest.mark.parametrize(
    "state",
    [
        LlmState("ready"),
        LlmState("waiting", "rate_limited"),
        LlmState("waiting", "budget_exhausted"),
        LlmState("waiting", "provider_error"),
        LlmState("failed", "keys_missing"),
        LlmState("failed", "provider_error"),
    ],
)
def test_every_state_is_a_valid_board_entry(state: LlmState) -> None:
    entry = make_report("llm", state.state, state.reason, llm_facts(TOTALS), NOW)

    assert (entry.state, entry.reason) == (state.state, state.reason)


def llm_entry(board: StatusBoard) -> LlmStatus:
    entry = board.snapshot().subsystems["llm"]
    assert isinstance(entry, LlmStatus)
    return entry


def test_the_tracker_reports_calls_in_flight_and_the_finished_totals() -> None:
    board = StatusBoard(clock=lambda: NOW)
    tracker = LlmStatusTracker(board)

    tracker.call_started("openai", "model-x")
    started = llm_entry(board)
    tracker.call_finished(record(), TOTALS)
    finished = llm_entry(board)

    assert started.state == "ready"
    assert started.facts == LlmFacts(
        provider="openai",
        model="model-x",
        in_flight=1,
        outcomes={outcome.value: 0 for outcome in CallOutcome},
    )
    assert finished.state == "ready"
    assert finished.facts == llm_facts(TOTALS, provider="openai", model="model-x")


def test_the_tracker_reports_a_retry_wait_with_its_time() -> None:
    board = StatusBoard(clock=lambda: NOW)
    tracker = LlmStatusTracker(board, clock=lambda: NOW)

    tracker.call_started("openai", "model-x")
    tracker.call_retrying(429, 40.0)
    rate_limited = llm_entry(board)
    tracker.call_retrying(503, 2.0)
    server_error = llm_entry(board)

    assert (rate_limited.state, rate_limited.reason) == ("waiting", "rate_limited")
    assert rate_limited.retry_at == NOW + 40.0
    assert (server_error.reason, server_error.retry_at) == ("provider_error", NOW + 2.0)


def test_the_tracker_reports_failures_and_the_exhausted_budget() -> None:
    board = StatusBoard(clock=lambda: NOW)
    budget = CallBudget(1)
    tracker = LlmStatusTracker(board, budget=budget)

    budget.take(1)
    tracker.call_started("openai", "model-x")
    tracker.call_finished(record(CallOutcome.HTTP_ERROR), TOTALS, http_status=500)
    after_failure = llm_entry(board)
    budget.take(1)
    tracker.refresh()
    after_refusal = llm_entry(board)

    assert (after_failure.state, after_failure.reason) == ("waiting", "budget_exhausted")
    assert after_failure.facts.in_flight == 0
    assert after_refusal.facts.calls_refused == 1


def test_a_finished_call_without_a_start_keeps_in_flight_at_zero() -> None:
    tracker = LlmStatusTracker(StatusBoard(clock=lambda: NOW))

    tracker.call_finished(record(), TOTALS)

    assert tracker.in_flight == 0
