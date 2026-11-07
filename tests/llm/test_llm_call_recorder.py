"""The recorder prices calls, keeps the crawl's totals and appends `llm_calls.jsonl`."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from crawlviz.llm import (
    LLM_CALLS_FILE_NAME,
    CallOutcome,
    CostTable,
    LlmCallRecord,
    LlmCallRecorder,
    ModelPrice,
)

STARTED = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
TABLE = CostTable(
    free_providers=frozenset({"ollama"}),
    prices={
        "openai": {
            "priced-model": ModelPrice(input_usd_per_million=1.0, output_usd_per_million=4.0)
        }
    },
)


def make_record(**changes: object) -> LlmCallRecord:
    fields: dict[str, object] = {
        "started_at": STARTED,
        "provider": "openai",
        "model": "priced-model",
        "input_tokens": 1_000_000,
        "output_tokens": 500_000,
        "latency_ms": 900.0,
        "attempts": 1,
        "outcome": "ok",
        "prompt_hash": "ab" * 32,
        "rendered_prompt": "[user]\npage text",
        "raw_reply": '{"results": {}}',
    }
    fields.update(changes)
    return LlmCallRecord.model_validate(fields)


async def test_totals_count_calls_tokens_cost_and_budget() -> None:
    recorder = LlmCallRecorder(None, cost_table=TABLE, budget_calls=3)
    await recorder.record(make_record())
    await recorder.record(make_record(cache_hit=True, attempts=0))
    await recorder.record(make_record(model="other-model", outcome="http_error"))
    await recorder.record(make_record(outcome="repaired"))
    totals = recorder.totals
    assert (totals.calls, totals.cache_hits) == (3, 1)
    assert (totals.failed_calls, totals.repaired_calls) == (1, 1)
    assert totals.input_tokens == 3_000_000  # the cache hit spent no tokens
    assert totals.estimated_cost_usd == pytest.approx(6.0)  # two priced calls, one cache hit
    assert totals.calls_without_price == 1
    assert (totals.budget_calls, totals.remaining_calls) == (3, 0)


@pytest.mark.parametrize(
    "outcome", ["invalid_output", "http_error", "network_error", "timeout", "bad_response"]
)
async def test_a_call_without_a_valid_answer_counts_as_failed(outcome: str) -> None:
    recorder = LlmCallRecorder(None)
    await recorder.record(make_record(outcome=outcome))
    assert recorder.totals.failed_calls == 1


async def test_totals_count_calls_by_outcome() -> None:
    recorder = LlmCallRecorder(None)
    assert set(recorder.totals.outcomes.values()) == {0}
    for outcome in ("ok", "ok", "timeout", "repaired"):
        await recorder.record(make_record(outcome=outcome))
    outcomes = recorder.totals.outcomes
    assert outcomes[CallOutcome.OK] == 2
    assert outcomes[CallOutcome.TIMEOUT] == outcomes[CallOutcome.REPAIRED] == 1
    assert sum(outcomes.values()) == 4
    assert set(outcomes) == set(CallOutcome)
    assert json.loads(recorder.totals.model_dump_json())["outcomes"]["timeout"] == 1


async def test_cost_is_unknown_until_a_priced_call_is_recorded() -> None:
    recorder = LlmCallRecorder(None)
    priced = await recorder.record(make_record())
    assert priced.cost_usd is None
    assert recorder.totals.estimated_cost_usd is None
    assert recorder.totals.remaining_calls is None


async def test_file_lines_leave_out_prompt_and_reply_unless_asked(tmp_path: Path) -> None:
    path = tmp_path / "run" / LLM_CALLS_FILE_NAME
    await LlmCallRecorder(path, cost_table=TABLE).record(make_record())
    await LlmCallRecorder(path, cost_table=TABLE, store_text=True).record(make_record())
    first, second = (json.loads(line) for line in path.read_text().splitlines())
    assert first["rendered_prompt"] is None and first["raw_reply"] is None
    assert first["prompt_hash"] == "ab" * 32
    assert first["cost_usd"] == pytest.approx(3.0)
    assert first["schema_version"] == 1
    assert second["rendered_prompt"] == "[user]\npage text"
    assert second["raw_reply"] == '{"results": {}}'


async def test_every_line_reads_back_as_a_call_record(tmp_path: Path) -> None:
    path = tmp_path / LLM_CALLS_FILE_NAME
    recorder = LlmCallRecorder(path, store_text=True)
    sent = [make_record(node_id=f"node-{index}") for index in range(5)]
    for record in sent:
        await recorder.record(record)
    stored = [LlmCallRecord.model_validate_json(line) for line in path.read_text().splitlines()]
    assert [record.node_id for record in stored] == [f"node-{index}" for index in range(5)]


async def test_a_failed_write_is_raised_after_the_call_is_counted(tmp_path: Path) -> None:
    blocker = tmp_path / "not_a_directory"
    blocker.write_text("")
    recorder = LlmCallRecorder(blocker / LLM_CALLS_FILE_NAME)
    with pytest.raises(OSError):
        await recorder.record(make_record())
    assert recorder.totals.calls == 1
