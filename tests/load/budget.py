"""The committed limits a load run is held to (``budget.json``).

A budget names the run it applies to (``smoke``, ``full``) and bounds each measurement.
Checking a measurement returns every limit it broke, in words, so a failed run says which
numbers to look at. The file is read with unknown keys refused, so a mistyped limit is an
error and never a limit that silently does not apply.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from tests.load.measurement import Measurement

BUDGET_FILE = Path(__file__).with_name("budget.json")
BUDGET_SCHEMA_VERSION = 1


class RunBudget(BaseModel):
    """Limits for one named run. A measurement must stay inside all of them."""

    model_config = ConfigDict(extra="forbid")

    max_wall_seconds: float = Field(gt=0)
    min_pages_per_second: float = Field(ge=0)
    max_peak_rss_mb: float = Field(gt=0)
    max_loop_lag_p99_ms: float = Field(gt=0)
    max_loop_lag_max_ms: float = Field(gt=0)


class Budget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int
    # Why the numbers are what they are; says "to be calibrated" until a measured run sets them.
    status: str
    runs: dict[str, RunBudget]

    def for_run(self, name: str) -> RunBudget:
        try:
            return self.runs[name]
        except KeyError:
            raise KeyError(
                f"{BUDGET_FILE.name} has no run {name!r}; it has {sorted(self.runs)}"
            ) from None


def load_budget(path: Path = BUDGET_FILE) -> Budget:
    budget = Budget.model_validate_json(path.read_text(encoding="utf-8"))
    if budget.schema_version != BUDGET_SCHEMA_VERSION:
        raise ValueError(
            f"{path.name} has schema_version {budget.schema_version}, "
            f"this harness reads {BUDGET_SCHEMA_VERSION}"
        )
    return budget


def check_budget(measurement: Measurement, limits: RunBudget) -> list[str]:
    """Every limit ``measurement`` broke, as a sentence; empty when the run is within budget."""
    problems: list[str] = []
    if measurement.wall_seconds > limits.max_wall_seconds:
        problems.append(
            f"wall time {measurement.wall_seconds:.1f} s is over {limits.max_wall_seconds:g} s"
        )
    if measurement.pages_per_second < limits.min_pages_per_second:
        problems.append(
            f"{measurement.pages_per_second:.1f} pages/s is under {limits.min_pages_per_second:g}"
        )
    if measurement.peak_rss_mb > limits.max_peak_rss_mb:
        problems.append(
            f"peak RSS {measurement.peak_rss_mb:.0f} MB is over {limits.max_peak_rss_mb:g} MB"
        )
    if measurement.loop_lag_p99_ms > limits.max_loop_lag_p99_ms:
        problems.append(
            f"event-loop lag p99 {measurement.loop_lag_p99_ms:.1f} ms "
            f"is over {limits.max_loop_lag_p99_ms:g} ms"
        )
    if measurement.loop_lag_max_ms > limits.max_loop_lag_max_ms:
        problems.append(
            f"event-loop lag max {measurement.loop_lag_max_ms:.1f} ms "
            f"is over {limits.max_loop_lag_max_ms:g} ms"
        )
    return problems
