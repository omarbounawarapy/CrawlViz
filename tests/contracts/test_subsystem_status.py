"""Subsystem status entries are typed per subsystem, and one report changes one entry."""

from typing import get_args

import pytest
from pydantic import ValidationError

from crawlviz.contracts import (
    SUBSYSTEMS,
    EmbedderFacts,
    LlmFacts,
    StatusBoardSnapshot,
    SubsystemStatus,
    apply_report,
    initial_board,
    make_report,
)
from crawlviz.llm import CallOutcome, LlmCallTotals

STARTED_AT = 1_000.0
LATER = 1_005.0


def test_the_subsystem_list_is_the_union_of_entry_models() -> None:
    entry_models = get_args(get_args(SubsystemStatus)[0])
    defaults = tuple(model.model_fields["subsystem"].default for model in entry_models)
    assert defaults == SUBSYSTEMS
    assert SUBSYSTEMS == ("embedder", "space", "llm", "fetch", "robots", "export")


def test_the_initial_board_has_every_subsystem_off_since_the_start() -> None:
    board = initial_board(STARTED_AT)

    assert tuple(board.subsystems) == SUBSYSTEMS
    assert {entry.state for entry in board.subsystems.values()} == {"off"}
    assert {entry.since for entry in board.subsystems.values()} == {STARTED_AT}


def test_a_report_builds_the_entry_of_its_subsystem_with_typed_facts() -> None:
    facts = EmbedderFacts(model="all-MiniLM-L6-v2", device="cpu")

    entry = make_report("embedder", "starting", "loading_model", facts, STARTED_AT)

    assert entry.subsystem == "embedder"
    assert entry.facts == facts


def test_a_reason_from_another_subsystem_is_refused() -> None:
    with pytest.raises(ValidationError, match="reason"):
        make_report("embedder", "waiting", "rate_limited", None, STARTED_AT)


def test_facts_of_another_subsystem_are_refused() -> None:
    with pytest.raises(ValidationError, match="facts"):
        make_report("embedder", "ready", None, LlmFacts(calls=1), STARTED_AT)


@pytest.mark.parametrize("state", ["waiting", "failed"])
def test_waiting_and_failed_need_a_reason(state: str) -> None:
    with pytest.raises(ValidationError, match="needs a reason code"):
        make_report("llm", state, None, None, STARTED_AT)  # type: ignore[arg-type]


def test_retry_at_belongs_to_a_waiting_status_only() -> None:
    waiting = make_report("llm", "waiting", "rate_limited", None, STARTED_AT, retry_at=LATER)
    assert waiting.retry_at == LATER

    with pytest.raises(ValidationError, match="retry_at is only for a 'waiting' status"):
        make_report("llm", "failed", "provider_error", None, STARTED_AT, retry_at=LATER)


def test_unknown_fact_keys_are_refused() -> None:
    with pytest.raises(ValidationError, match="extra"):
        EmbedderFacts.model_validate({"model": "m", "gpu": True})


def test_a_board_without_every_subsystem_is_refused() -> None:
    board = initial_board(STARTED_AT)
    partial = {name: board.subsystems[name] for name in SUBSYSTEMS[:-1]}

    with pytest.raises(ValidationError, match="one entry for each"):
        StatusBoardSnapshot(subsystems=partial)


def test_a_board_entry_under_the_wrong_name_is_refused() -> None:
    board = initial_board(STARTED_AT)
    swapped = dict(board.subsystems)
    swapped["space"] = board.subsystems["embedder"]

    with pytest.raises(ValidationError, match="the entry under 'space' is for 'embedder'"):
        StatusBoardSnapshot(subsystems=swapped)


def test_a_report_replaces_only_its_own_entry() -> None:
    board = initial_board(STARTED_AT)
    report = make_report("llm", "waiting", "rate_limited", None, LATER, retry_at=LATER + 40)

    after = apply_report(board, report)

    assert after.subsystems["llm"] == report
    assert {name: e for name, e in after.subsystems.items() if name != "llm"} == {
        name: e for name, e in board.subsystems.items() if name != "llm"
    }
    assert board.subsystems["llm"].state == "off"  # the reducer is pure


def test_since_stays_while_the_state_and_reason_stay() -> None:
    board = apply_report(
        initial_board(STARTED_AT),
        make_report("llm", "ready", None, LlmFacts(calls=1), STARTED_AT),
    )

    after = apply_report(board, make_report("llm", "ready", None, LlmFacts(calls=2), LATER))

    assert after.subsystems["llm"].since == STARTED_AT
    assert after.subsystems["llm"].facts == LlmFacts(calls=2)


def test_since_moves_when_the_reason_changes() -> None:
    board = apply_report(
        initial_board(STARTED_AT),
        make_report("llm", "waiting", "rate_limited", None, STARTED_AT),
    )

    after = apply_report(board, make_report("llm", "waiting", "budget_exhausted", None, LATER))

    assert after.subsystems["llm"].since == LATER


def test_a_report_that_changes_nothing_returns_the_same_board() -> None:
    board = apply_report(
        initial_board(STARTED_AT), make_report("fetch", "ready", None, None, STARTED_AT)
    )

    assert apply_report(board, make_report("fetch", "ready", None, None, LATER)) is board


def test_the_board_round_trips_through_json() -> None:
    board = apply_report(
        initial_board(STARTED_AT),
        make_report("embedder", "starting", "loading_model", EmbedderFacts(model="m"), LATER),
    )

    assert StatusBoardSnapshot.model_validate_json(board.model_dump_json()) == board


def test_llm_outcome_counts_accept_every_call_outcome_code() -> None:
    counts = {outcome.value: 1 for outcome in CallOutcome}

    assert LlmFacts(outcomes=counts).outcomes == counts


@pytest.mark.parametrize("code", ["Rate Limited", "rate-limited", "", "x" * 65])
def test_llm_outcome_keys_must_be_snake_case_codes(code: str) -> None:
    with pytest.raises(ValidationError, match="outcomes"):
        LlmFacts(outcomes={code: 1})


def test_llm_facts_use_the_names_of_the_call_totals() -> None:
    shared = set(LlmFacts.model_fields) & set(LlmCallTotals.model_fields)

    assert shared >= {"calls", "cache_hits", "failed_calls", "input_tokens", "output_tokens"}
    assert shared >= {"budget_calls", "estimated_cost_usd", "outcomes"}


def test_negative_counts_are_refused() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        LlmFacts(calls=-1)
