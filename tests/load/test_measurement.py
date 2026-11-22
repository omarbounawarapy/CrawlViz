"""What a load run records: peak memory is read from the kernel, and a measurement is JSON."""

import json

from tests.load.measurement import Measurement, get_peak_rss_mb

PLAUSIBLE_MIN_RSS_MB = 10
PLAUSIBLE_MAX_RSS_MB = 100_000


def test_peak_rss_is_a_plausible_number_of_megabytes() -> None:
    peak = get_peak_rss_mb()

    assert PLAUSIBLE_MIN_RSS_MB < peak < PLAUSIBLE_MAX_RSS_MB


def test_a_measurement_round_trips_through_json() -> None:
    measurement = Measurement(
        page_budget=200,
        fetched_pages=201,
        wall_seconds=4.5,
        pages_per_second=44.7,
        peak_rss_mb=410.0,
        loop_lag_samples=450,
        loop_lag_p50_ms=0.2,
        loop_lag_p99_ms=3.0,
        loop_lag_max_ms=12.0,
        stop_reason="MAX_NODES_REACHED",
        event_counts={"PageFetchedEvent": 201},
    )

    assert json.loads(json.dumps(measurement.to_json())) == {
        "page_budget": 200,
        "fetched_pages": 201,
        "wall_seconds": 4.5,
        "pages_per_second": 44.7,
        "peak_rss_mb": 410.0,
        "loop_lag_samples": 450,
        "loop_lag_p50_ms": 0.2,
        "loop_lag_p99_ms": 3.0,
        "loop_lag_max_ms": 12.0,
        "stop_reason": "MAX_NODES_REACHED",
        "event_counts": {"PageFetchedEvent": 201},
    }
