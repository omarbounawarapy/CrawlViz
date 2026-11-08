"""Per-model token prices and the cost estimate of one call.

Prices change without notice, so none are built in: they come from a JSON file
the operator keeps (format below), and every figure computed from them is an
estimate. A model with no price has no cost estimate, not a cost of zero.
Providers listed in `free_providers` (local servers) cost nothing.

File format::

    {
      "schema_version": 1,
      "as_of": "2026-10-30",
      "free_providers": ["ollama", "vllm", "lmstudio", "llamacpp"],
      "prices": {
        "openai": {"gpt-4o-mini": {"input_usd_per_million": 0.15,
                                   "output_usd_per_million": 0.6}}
      }
    }
"""

from datetime import date
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from .types import TokenUsage

COST_TABLE_SCHEMA_VERSION: Final = 1
TOKENS_PER_PRICE_UNIT = 1_000_000
MAX_COST_TABLE_BYTES = 1024 * 1024


class ModelPrice(BaseModel):
    """US dollars per million tokens, input and output priced apart."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_usd_per_million: float = Field(ge=0)
    output_usd_per_million: float = Field(ge=0)

    def cost_usd(self, usage: TokenUsage) -> float:
        return (
            usage.input_tokens * self.input_usd_per_million
            + usage.output_tokens * self.output_usd_per_million
        ) / TOKENS_PER_PRICE_UNIT


class CostTable(BaseModel):
    """Prices by provider, then model id, as of one date."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = COST_TABLE_SCHEMA_VERSION
    as_of: date | None = None
    free_providers: frozenset[str] = frozenset()
    prices: dict[str, dict[str, ModelPrice]] = Field(default_factory=dict)

    def price_for(self, provider: str, model: str) -> ModelPrice | None:
        return self.prices.get(provider, {}).get(model)

    def estimate_cost_usd(self, provider: str, model: str, usage: TokenUsage) -> float | None:
        """Estimated dollars for `usage` on `model`, or None when the model has no price."""
        if provider in self.free_providers:
            return 0.0
        price = self.price_for(provider, model)
        return None if price is None else price.cost_usd(usage)


def load_cost_table(path: Path) -> CostTable:
    """Read and validate a cost table file; read it once, before the crawl starts.

    Raises:
        ValueError: If the file is over the size limit, or is not a valid table
            (pydantic's ValidationError is a ValueError and names the field).
        OSError: If the file cannot be read.
    """
    size = path.stat().st_size
    if size > MAX_COST_TABLE_BYTES:
        raise ValueError(f"{path}: {size} bytes, over the {MAX_COST_TABLE_BYTES} limit")
    return CostTable.model_validate_json(path.read_bytes())
