"""The typed request, response and call record refuse malformed values and keep keys out."""

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from crawlviz.llm import (
    CallOutcome,
    ChatRole,
    LlmCallError,
    LlmCallRecord,
    LlmMessage,
    LlmRequest,
    LlmResponse,
    LlmTimeoutError,
    TokenUsage,
    render_messages,
)

STARTED = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def make_request(**changes: object) -> LlmRequest:
    fields: dict[str, object] = {
        "provider": "ollama",
        "model": "llama3.1:8b",
        "messages": (
            LlmMessage(role=ChatRole.SYSTEM, content="Score links."),
            LlmMessage(role=ChatRole.USER, content="page text"),
        ),
        "prompt_id": "link_scoring",
        "prompt_hash": "ab" * 32,
        "temperature": 0.0,
        "crawl_id": "crawl-1",
        "node_id": "node-7",
    }
    fields.update(changes)
    return LlmRequest.model_validate(fields)


def test_request_needs_at_least_one_message() -> None:
    with pytest.raises(ValidationError):
        make_request(messages=())


def test_request_refuses_unknown_fields_and_negative_temperature() -> None:
    with pytest.raises(ValidationError):
        make_request(api_key="sk-secret")
    with pytest.raises(ValidationError):
        make_request(temperature=-0.1)


def test_request_is_immutable() -> None:
    request = make_request()
    with pytest.raises(ValidationError):
        request.model = "other"


def test_record_from_response_carries_every_figure() -> None:
    response = LlmResponse(
        text='{"results": {}}',
        model="llama3.1:8b",
        usage=TokenUsage(input_tokens=120, output_tokens=30),
        attempts=2,
        latency_ms=850.0,
    )
    record = LlmCallRecord.from_response(make_request(), response, started_at=STARTED, cost_usd=0.0)
    assert record.schema_version == 1
    assert (record.input_tokens, record.output_tokens) == (120, 30)
    assert (record.attempts, record.latency_ms, record.cache_hit) == (2, 850.0, False)
    assert record.outcome is CallOutcome.OK
    assert record.prompt_hash == "ab" * 32
    assert record.temperature == 0.0
    assert record.raw_reply == '{"results": {}}'
    assert record.rendered_prompt == "[system]\nScore links.\n\n[user]\npage text"


def test_both_records_carry_the_sampling_settings_sent() -> None:
    request = make_request(temperature=0.7, reasoning_effort="low")
    response = LlmResponse(text="{}", model="m", attempts=1, latency_ms=1.0)
    error = LlmCallError("failed", outcome=CallOutcome.HTTP_ERROR, attempts=1, latency_ms=1.0)
    for record in (
        LlmCallRecord.from_response(request, response, started_at=STARTED),
        LlmCallRecord.from_error(request, error, started_at=STARTED),
    ):
        assert (record.temperature, record.reasoning_effort) == (0.7, "low")


def test_an_unset_reasoning_effort_is_recorded_as_the_provider_default() -> None:
    assert make_request().reasoning_effort is None
    with pytest.raises(ValidationError):
        make_request(reasoning_effort="")


def test_record_from_error_keeps_the_outcome_and_message() -> None:
    error = LlmCallError(
        "ollama/llama3.1:8b answered HTTP 503",
        outcome=CallOutcome.HTTP_ERROR,
        attempts=4,
        latency_ms=7000.0,
        status=503,
    )
    record = LlmCallRecord.from_error(make_request(), error, started_at=STARTED)
    assert record.outcome is CallOutcome.HTTP_ERROR
    assert record.attempts == 4
    assert record.error == "ollama/llama3.1:8b answered HTTP 503"
    assert record.raw_reply is None


def test_a_timeout_is_a_typed_call_error_and_a_timeout_error() -> None:
    error = LlmTimeoutError("ollama/llama3.1:8b gave no answer", attempts=1, latency_ms=60_000.0)
    assert isinstance(error, LlmCallError) and isinstance(error, TimeoutError)
    assert str(error) == "ollama/llama3.1:8b gave no answer"
    record = LlmCallRecord.from_error(make_request(), error, started_at=STARTED)
    assert record.outcome is CallOutcome.TIMEOUT
    assert (record.attempts, record.latency_ms) == (1, 60_000.0)


def test_record_round_trips_through_json() -> None:
    response = LlmResponse(text="{}", model="m", attempts=0, latency_ms=0.0, cache_hit=True)
    record = LlmCallRecord.from_response(make_request(), response, started_at=STARTED)
    line = record.model_dump_json()
    assert LlmCallRecord.model_validate_json(line) == record
    assert json.loads(line)["cache_hit"] is True


def test_record_refuses_an_unknown_schema_version() -> None:
    with pytest.raises(ValidationError):
        LlmCallRecord.model_validate(
            {
                "schema_version": 2,
                "started_at": STARTED,
                "provider": "p",
                "model": "m",
                "latency_ms": 0.0,
                "attempts": 1,
                "outcome": "ok",
            }
        )


def test_render_messages_labels_each_role() -> None:
    messages = (LlmMessage(role=ChatRole.USER, content="hi"),)
    assert render_messages(messages) == "[user]\nhi"
