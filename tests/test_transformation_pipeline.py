import json
import logging
from pathlib import Path

from pipelines.transformation_pipeline import MAX_REGEX_INPUT_CHARS, TransformationPipeline

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
