"""What a load run records, and how it is read from the process."""

import resource
import sys
from dataclasses import asdict, dataclass
from typing import Any

BYTES_PER_MB = 1024 * 1024
# ru_maxrss is in kilobytes on Linux and in bytes on macOS.
RU_MAXRSS_BYTES_PER_UNIT = 1 if sys.platform == "darwin" else 1024


def get_peak_rss_mb() -> float:
    """Highest resident set size this process has reached, in megabytes.

    ``getrusage`` is used and not ``tracemalloc`` because the kernel counts every page
    the process holds, native memory included (numpy, lxml, the interpreter's own
    arenas), and costs the crawl nothing. ``tracemalloc`` sees only Python allocations
    and slows a crawl several times over, which would change what is measured.
    The value never goes down, so a run is measured in its own process.
    """
    peak_units = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak_units * RU_MAXRSS_BYTES_PER_UNIT / BYTES_PER_MB


@dataclass(frozen=True)
class Measurement:
    """One load run. ``fetched_pages`` is what the site served; ``FetchStage`` holds the page
    budget, so a run that reaches it served exactly ``page_budget`` pages.
    ``event_counts`` maps an event type name to how many were emitted; ``stop_reason`` is the
    reason on the stop event."""

    page_budget: int
    fetched_pages: int
    wall_seconds: float
    pages_per_second: float
    peak_rss_mb: float
    loop_lag_samples: int
    loop_lag_p50_ms: float
    loop_lag_p99_ms: float
    loop_lag_max_ms: float
    stop_reason: str
    event_counts: dict[str, int]

    def to_json(self) -> dict[str, Any]:  # Any: the JSON the report prints
        return asdict(self)
