import json
from pathlib import Path

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
