"""Every stored format loads from each of its versions, and writes the current one."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from config.blueprint_schema import validate_blueprint
from config.settings_store import load_runtime_config, read_stored
from crawlviz.contracts import (
    SCHEMA_VERSION_KEY,
    MigrationChain,
    SchemaVersionError,
    StoredFormatError,
    rename_pipeline_settings,
)
from crawlviz.contracts.stored_formats import (
    BLUEPRINT_FILE,
    PRESETS_FILE,
    RUN_MANIFEST,
    SETTINGS_FILE,
    STORED_FORMATS,
    dump_blueprint_document,
    dump_presets_document,
    dump_run_manifest,
    dump_settings_document,
    load_blueprint_document,
    load_presets_document,
    load_run_manifest,
    load_settings_document,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
BLUEPRINT_TEMPLATES = sorted((ROOT / "templates").glob("*.json"))


def _fixture(format_name: str, version: int) -> dict[str, Any]:
    path = FIXTURES / format_name / f"v{version}.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _assert_applied(patch: dict[str, Any], effective: dict[str, Any], where: str = "") -> None:
    """Every value in ``patch`` is the value in effect, so no key was silently dropped."""
    for key, value in patch.items():
        assert key in effective, f"{where}{key} is not a setting"
        if isinstance(value, dict):
            _assert_applied(value, effective[key], f"{where}{key}.")
        else:
            assert effective[key] == value, f"{where}{key}"


# Each format with the reader a stored file of that format goes through.
READERS: list[tuple[MigrationChain, Callable[[dict[str, Any]], object]]] = [
    (SETTINGS_FILE, load_settings_document),
    (PRESETS_FILE, load_presets_document),
    (BLUEPRINT_FILE, load_blueprint_document),
    (RUN_MANIFEST, load_run_manifest),
]


def test_every_stored_format_has_a_reader() -> None:
    assert [chain for chain, _ in READERS] == list(STORED_FORMATS)


@pytest.mark.parametrize("chain", STORED_FORMATS, ids=lambda c: c.format_name)
def test_every_stored_format_has_a_step_for_every_older_version(chain: MigrationChain) -> None:
    assert chain.missing_steps() == []


@pytest.mark.parametrize(
    ("chain", "read"), READERS, ids=[chain.format_name for chain, _ in READERS]
)
def test_a_file_from_a_newer_crawlviz_is_refused_in_plain_words(
    chain: MigrationChain, read: Callable[[dict[str, Any]], object]
) -> None:
    newer = chain.current_version + 1
    expected = (
        rf"The {chain.format_name} is version {newer}, but this CrawlViz reads version "
        rf"{chain.current_version} at most\. Update CrawlViz to open it\."
    )
    with pytest.raises(SchemaVersionError, match=expected):
        read({SCHEMA_VERSION_KEY: newer})


@pytest.mark.parametrize("version", [0, 1, 2])
def test_each_settings_version_loads_as_the_same_valid_patch(version: int) -> None:
    patch = load_settings_document(_fixture("settings", version))
    assert SCHEMA_VERSION_KEY not in patch
    assert patch == SETTINGS_FILE.strip(_fixture("settings", 2))
    # The loaded patch is what RuntimeConfig accepts today, every value taking effect.
    _assert_applied(patch, load_runtime_config(None, patch).model_dump())


def test_a_version_one_settings_file_gets_the_pipeline_section_names() -> None:
    old = _fixture("settings", 1)
    assert old["pipelines"] == {"requests": {"workers": 2}}
    assert load_settings_document(old)["pipelines"] == {"fetch": {"workers": 2}}
    assert load_settings_document(old) == SETTINGS_FILE.strip(rename_pipeline_settings(old))


def test_a_version_one_settings_file_with_a_section_under_both_names_is_refused() -> None:
    both = {SCHEMA_VERSION_KEY: 1, "pipelines": {"requests": {}, "fetch": {}}}
    with pytest.raises(StoredFormatError, match=r"Keep only pipelines\.fetch\."):
        load_settings_document(both)


def test_an_unversioned_settings_file_on_disk_still_loads(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text((FIXTURES / "settings" / "v0.json").read_text(encoding="utf-8"))
    patch = read_stored(settings_file)
    assert patch == SETTINGS_FILE.strip(_fixture("settings", 2))
    _assert_applied(patch, load_runtime_config(None, patch).model_dump())


def test_settings_are_written_at_the_current_version() -> None:
    patch = load_settings_document(_fixture("settings", 0))
    assert dump_settings_document(patch) == _fixture("settings", 2)
    assert SETTINGS_FILE.current_version == 2


def test_settings_survive_a_write_and_read_unchanged() -> None:
    patch = load_settings_document(_fixture("settings", 0))
    assert load_settings_document(dump_settings_document(patch)) == patch


@pytest.mark.parametrize("version", [0, 1])
def test_each_presets_version_loads_as_the_same_presets(version: int) -> None:
    presets = load_presets_document(_fixture("presets", version))
    assert presets == _fixture("presets", 1)["presets"]
    for values in presets.values():
        _assert_applied(values, load_runtime_config(None, values).model_dump())


def test_presets_are_written_at_the_current_version() -> None:
    presets = load_presets_document(_fixture("presets", 0))
    assert dump_presets_document(presets) == _fixture("presets", 1)
    assert PRESETS_FILE.version_of(dump_presets_document(presets)) == 1


def test_a_version_zero_preset_named_like_the_version_key_keeps_its_name() -> None:
    patch = {"fetch": {"min_delay": 3.0}}
    presets = load_presets_document({SCHEMA_VERSION_KEY: patch, "other": {}})
    assert presets == {SCHEMA_VERSION_KEY: patch, "other": {}}
    assert load_presets_document(dump_presets_document(presets)) == presets


def test_a_presets_file_with_the_wrong_shape_says_how_to_recover() -> None:
    with pytest.raises(StoredFormatError, match="delete the file"):
        load_presets_document({SCHEMA_VERSION_KEY: 1, "presets": []})


@pytest.mark.parametrize("path", BLUEPRINT_TEMPLATES, ids=lambda p: p.name)
def test_every_shipped_blueprint_loads_unchanged_and_still_validates(path: Path) -> None:
    stored = json.loads(path.read_text(encoding="utf-8"))
    blueprint = load_blueprint_document(stored)
    assert blueprint == BLUEPRINT_FILE.strip(stored)
    validate_blueprint(blueprint)
    assert load_blueprint_document(dump_blueprint_document(blueprint)) == blueprint


def test_an_unversioned_run_manifest_loads_with_every_field_kept() -> None:
    stored = _fixture("run_manifest", 0)
    manifest = load_run_manifest(stored)
    assert manifest == {**stored, SCHEMA_VERSION_KEY: RUN_MANIFEST.current_version}
    assert load_run_manifest(dump_run_manifest(stored)) == manifest
