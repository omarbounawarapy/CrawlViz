"""A run's manifest.json is a versioned record: the version is part of it."""

import json
from pathlib import Path

from config.runtime_config import default_runtime_config
from core.run_manifest import RunManifestWriter
from crawlviz.contracts import load_run_manifest
from ui_bridge.event_recorder import EventRecorder


def _write_manifest(run_dir: Path) -> dict:
    writer = RunManifestWriter(
        crawl_id="crawl-1",
        blueprint={"blueprint_id": "bp"},
        config=default_runtime_config(),
        model_information="model-x",
        seed=7,
        fetch_concurrency=2,
        scoring_concurrency=3,
    )
    recorder = EventRecorder(run_dir)
    writer.write(recorder)
    recorder.close()
    return json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))


def test_the_manifest_carries_the_schema_version(tmp_path: Path) -> None:
    assert _write_manifest(tmp_path / "run")["schema_version"] == 2


def test_the_manifest_keeps_every_field_it_had(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "run")
    assert manifest["crawl_id"] == "crawl-1"
    assert manifest["seed"] == 7
    assert manifest["blueprint"] == {"blueprint_id": "bp"}
    assert manifest["scoring_concurrency"] == 3


def test_a_written_manifest_loads_back_unchanged(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "run")
    assert load_run_manifest(manifest) == manifest
