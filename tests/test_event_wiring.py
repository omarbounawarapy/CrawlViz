"""Regression coverage for Crawler's event subscription wiring.

core/crawler.py's _wire_subscriptions is a flat, hand-maintained list mapping
event types to the pipelines that should receive them. That shape makes it
easy for a pipeline to be built to handle an event (its handler table maps
it) without ever being subscribed to receive it -- which is exactly what
happened to HighScoreLinksEvent: PriorityPipeline has always known how to
process it, but nothing subscribed PriorityPipeline to receive it, so every
link the cascade was confident enough to trust without an LLM call was
silently dropped from the crawl instead of being fast-tracked into it.

This suite builds a real Crawler, drives it through the same construction
path core/crawler.py.start() uses, and asserts directly against the live
EventBroker registry -- so a future edit that reintroduces this class of gap
(or a new one like it) fails a test instead of waiting for another audit.
"""
import pytest

from core.crawler import Crawler
from events import (
    FilteringPipelineErrorEvent,
    HighScoreLinksEvent,
    LowScoreLinksEvent,
    ProcessingExtractionFailedEvent,
)

FAKE_BLUEPRINT = {
    "blueprint_id": "test-bp",
    "target_topic": "test topic",
    "extraction": {"fields": []},
    "expansion": {},
    "scoring": {
        "strategy": "TOPICAL",
        "params": {"scoring_type": "topical", "model_information": {}},
    },
    "stop_conditions": {
        "max_nodes": 50, "max_depth": 3, "max_duration": 60,
        "no_progress_timeout": 30, "stop_url": None,
        "priority_strategy": "balanced",
    },
}


class Fake:
    """Stand-in for nlp_service / scoring_service / space_updater -- none of
    these get their methods called during pipeline construction or
    subscription wiring, only stored as attributes, so an inert object is
    sufficient for this test's purposes."""
    def __getattr__(self, name):
        return Fake()

    def __call__(self, *a, **k):
        return Fake()


@pytest.fixture
def wired_crawler():
    crawler = Crawler("wikiMD.json")
    crawler._load_blueprint_config(FAKE_BLUEPRINT)
    pipelines = crawler._build_pipelines(FAKE_BLUEPRINT, Fake(), Fake())
    crawler._wire_subscriptions(pipelines, Fake())
    crawler._build_ui_layer(pipelines)
    return crawler


def consumers_of(crawler, event_type):
    registry = crawler.event_broker.registry.registry
    return [type(c).__name__ for c in registry.get(event_type, [])]


class TestCascadeSubscriptionGap:
    """Guards the fix for the HighScoreLinksEvent bug described above."""

    def test_priority_pipeline_receives_high_score_links(self, wired_crawler):
        consumers = consumers_of(wired_crawler, HighScoreLinksEvent)
        assert "PriorityPipeline" in consumers, (
            "PriorityPipeline is not subscribed to HighScoreLinksEvent -- "
            "high-confidence links will be scored, bucketed, and then "
            "silently dropped instead of fast-tracked into the frontier."
        )

    def test_telemetry_bridge_receives_both_cascade_decision_events(self, wired_crawler):
        for event_type in (HighScoreLinksEvent, LowScoreLinksEvent):
            consumers = consumers_of(wired_crawler, event_type)
            assert "TelemetryBridge" in consumers, (
                f"TelemetryBridge is not subscribed to {event_type.__name__} -- "
                "the cascade's decision trail (which candidates were "
                "trusted/dropped) would not reach the UI."
            )


class TestFailureEventsAreNoLongerSilent:
    """Guards the fix for the two previously-orphaned failure events: before
    this, an extraction or filtering exception produced no log line and no
    UI signal anywhere."""

    @pytest.mark.parametrize("event_type", [FilteringPipelineErrorEvent, ProcessingExtractionFailedEvent])
    def test_failure_reaches_debug_log_and_ui(self, wired_crawler, event_type):
        consumers = consumers_of(wired_crawler, event_type)
        assert "DebuggingPipeline" in consumers
        assert "TelemetryBridge" in consumers


class TestTelemetryBridgeCoverage:
    def test_subscribed_to_substantially_more_than_the_v1_translator(self, wired_crawler):
        registry = wired_crawler.event_broker.registry.registry
        subscribed = [
            event_type for event_type, consumers in registry.items()
            if any(type(c).__name__ == "TelemetryBridge" for c in consumers)
        ]
        # V1's UIEventTranslator subscribed to 7 event types.
        assert len(subscribed) >= 30
