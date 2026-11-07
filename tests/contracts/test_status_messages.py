"""The SUBSYSTEM_STATUS message carries one whole entry, and the crawl states are one list."""

import json

import pytest
from pydantic import ValidationError

from crawlviz.contracts import (
    CRAWL_END_STATES,
    CRAWL_STATES,
    SUBSYSTEM_STATUS,
    LlmFacts,
    SubsystemStatusMessage,
    make_report,
)

SENT_AT = 1_010.0


def test_the_message_serialises_its_type_and_the_whole_entry() -> None:
    entry = make_report("llm", "waiting", "rate_limited", LlmFacts(calls=3), 1_000.0, 1_040.0)

    wire = json.loads(SubsystemStatusMessage(ts=SENT_AT, entry=entry).model_dump_json())

    assert wire["type"] == SUBSYSTEM_STATUS
    assert wire["ts"] == SENT_AT
    assert wire["entry"]["subsystem"] == "llm"
    assert wire["entry"]["retry_at"] == 1_040.0
    assert wire["entry"]["facts"]["calls"] == 3


def test_the_message_round_trips_to_the_same_entry_model() -> None:
    entry = make_report("robots", "failed", "rules_unavailable", None, 1_000.0)
    message = SubsystemStatusMessage(ts=SENT_AT, entry=entry)

    assert SubsystemStatusMessage.model_validate_json(message.model_dump_json()) == message


def test_another_message_type_is_refused() -> None:
    entry = make_report("fetch", "ready", None, None, 1_000.0)

    with pytest.raises(ValidationError, match="type"):
        SubsystemStatusMessage.model_validate(
            {"type": "NODE_ADDED", "ts": SENT_AT, "entry": entry.model_dump()}
        )


def test_the_end_states_are_the_last_crawl_states() -> None:
    assert CRAWL_STATES[: -len(CRAWL_END_STATES)] == ("idle", "starting", "running", "stopping")
    assert CRAWL_STATES[-len(CRAWL_END_STATES) :] == CRAWL_END_STATES
