import json
import logging
from pathlib import Path

from config import MAX_REGEX_INPUT_CHARS
from events import (
    ContentFilteredEvent,
    TransformationCompletedEvent,
    TransformationStepSkippedEvent,
)
from pipelines.transformation_pipeline import TransformationPipeline

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "wikiMD.json"


def test_wikimd_transforms_are_applied():
    extraction = json.loads(TEMPLATE.read_text())["extraction"]
    fields = extraction["fields"]
    lowered = [
        name
        for name, spec in fields.items()
        if any(t.get("type") == "lowercase" for t in spec.get("transform", []))
    ]
    assert lowered, "wikiMD.json should declare a lowercase transform"

    pipeline = TransformationPipeline(event_broker=None, extraction_blueprint=extraction)
    item = {name: "  MiXeD Case  " for name in lowered}
    [(out, h)] = pipeline._transform_items([(item, "h")], node=None)

    for name in lowered:
        assert out[name] == out[name].lower()
        assert out[name] != "  MiXeD Case  "
    assert h == "h"


def _pipeline() -> TransformationPipeline:
    return TransformationPipeline(event_broker=None, extraction_blueprint={})


def test_regex_skips_input_over_the_limit_and_logs(caplog):
    long_text = "a" * (MAX_REGEX_INPUT_CHARS + 1)
    with caplog.at_level(logging.WARNING, logger="pipelines.transformation_pipeline"):
        result = _pipeline()._regex(long_text, {"type": "regex", "pattern": "(a+)"})

    assert result == long_text
    assert "Skipping regex transform" in caplog.text


def test_regex_extract_skips_input_over_the_limit_and_logs(caplog):
    long_text = "a" * (MAX_REGEX_INPUT_CHARS + 1)
    with caplog.at_level(logging.WARNING, logger="pipelines.transformation_pipeline"):
        result = _pipeline()._regex_extract(long_text, {"type": "regex_extract", "pattern": "a"})

    assert result == long_text
    assert "Skipping regex_extract transform" in caplog.text


def test_regex_still_matches_input_at_the_limit():
    text = "x" * (MAX_REGEX_INPUT_CHARS - 1) + "7"
    result = _pipeline()._regex(text, {"type": "regex", "pattern": r"(\d)$"})

    assert result == "7"


def test_the_regex_cap_is_a_setting_of_the_pipeline():
    pipeline = TransformationPipeline(
        event_broker=None, extraction_blueprint={}, max_regex_input_chars=10
    )

    assert pipeline._regex("a" * 11, {"type": "regex", "pattern": "(a+)"}) == "a" * 11
    assert pipeline._regex("a" * 10, {"type": "regex", "pattern": "(a+)"}) == "a" * 10
    assert pipeline._skipped_steps == [("regex", 11)]


class FakeBroker:
    def __init__(self):
        self.emitted = []

    async def emit(self, event):
        self.emitted.append(event)


class FakeNode:
    def get_id(self):
        return 7


def _filtered(items):
    return ContentFilteredEvent(
        correlation_id="7",
        node=FakeNode(),
        links=[],
        items=items,
        accepted_links_count=0,
        rejected_links_count=0,
        accepted_items_count=len(items),
        rejected_items_count=0,
    )


async def test_a_skipped_step_is_reported_and_the_page_still_completes():
    broker = FakeBroker()
    extraction = {"fields": {"title": {"transform": [{"type": "regex", "pattern": "(a+)"}]}}}
    pipeline = TransformationPipeline(broker, extraction, max_regex_input_chars=10)

    await pipeline._process(_filtered([({"title": "a" * 11}, "h")]), worker_id=0)

    skipped = [e for e in broker.emitted if isinstance(e, TransformationStepSkippedEvent)]
    [completed] = [e for e in broker.emitted if isinstance(e, TransformationCompletedEvent)]
    assert [(e.transform_type, e.input_length, e.limit) for e in skipped] == [("regex", 11, 10)]
    assert completed.transformed_items == [({"title": "a" * 11}, "h")]


async def test_no_skip_is_reported_when_every_step_fits():
    broker = FakeBroker()
    extraction = {"fields": {"title": {"transform": [{"type": "regex", "pattern": "(a+)"}]}}}
    pipeline = TransformationPipeline(broker, extraction)

    await pipeline._process(_filtered([({"title": "aaa"}, "h")]), worker_id=0)

    assert not [e for e in broker.emitted if isinstance(e, TransformationStepSkippedEvent)]
