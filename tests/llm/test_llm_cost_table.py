"""Cost estimates come from the price table only; unpriced models have no estimate."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from crawlviz.score.llm import CostTable, ModelPrice, TokenUsage, load_cost_table
from crawlviz.score.llm.cost_table import MAX_COST_TABLE_BYTES

TABLE = CostTable(
    free_providers=frozenset({"ollama"}),
    prices={
        "openai": {
            "priced-model": ModelPrice(input_usd_per_million=1.0, output_usd_per_million=4.0)
        }
    },
)


def test_cost_is_priced_per_million_tokens_in_and_out() -> None:
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=500_000)
    assert TABLE.estimate_cost_usd("openai", "priced-model", usage) == pytest.approx(3.0)


def test_unpriced_model_has_no_estimate_and_free_providers_cost_nothing() -> None:
    usage = TokenUsage(input_tokens=10, output_tokens=10)
    assert TABLE.estimate_cost_usd("openai", "other-model", usage) is None
    assert TABLE.estimate_cost_usd("ollama", "llama3.1:8b", usage) == 0.0


def test_load_cost_table_reads_the_documented_format(tmp_path: Path) -> None:
    path = tmp_path / "prices.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "as_of": "2026-10-30",
                "free_providers": ["ollama"],
                "prices": {
                    "openai": {"m": {"input_usd_per_million": 0.15, "output_usd_per_million": 0.6}}
                },
            }
        )
    )
    table = load_cost_table(path)
    assert table.price_for("openai", "m") == ModelPrice(
        input_usd_per_million=0.15, output_usd_per_million=0.6
    )
    assert "ollama" in table.free_providers


def test_load_cost_table_refuses_unknown_keys_and_negative_prices(tmp_path: Path) -> None:
    path = tmp_path / "prices.json"
    path.write_text('{"schema_version": 1, "currency": "EUR"}')
    with pytest.raises(ValidationError):
        load_cost_table(path)
    path.write_text(
        '{"prices": {"p": {"m": {"input_usd_per_million": -1, "output_usd_per_million": 0}}}}'
    )
    with pytest.raises(ValidationError):
        load_cost_table(path)


def test_load_cost_table_refuses_oversized_files(tmp_path: Path) -> None:
    path = tmp_path / "prices.json"
    path.write_text(" " * (MAX_COST_TABLE_BYTES + 1))
    with pytest.raises(ValueError, match="over the"):
        load_cost_table(path)
