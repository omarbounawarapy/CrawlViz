"""MigrationChain brings any older document to the current version, one step at a time."""

from typing import Any

import pytest

from crawlviz.contracts import (
    SCHEMA_VERSION_KEY,
    MigrationChain,
    SchemaVersionError,
    unchanged,
)


def _rename_name_to_title(doc: dict[str, Any]) -> dict[str, Any]:
    doc["title"] = doc.pop("name")
    return doc


def _add_tags(doc: dict[str, Any]) -> dict[str, Any]:
    doc.setdefault("tags", [])
    return doc


def _two_step_chain() -> MigrationChain:
    chain = MigrationChain("example file", current_version=2)
    chain.register(0, _rename_name_to_title)
    chain.register(1, _add_tags)
    return chain


def test_a_document_without_a_version_is_version_zero_and_runs_every_step() -> None:
    migrated = _two_step_chain().migrate({"name": "a"})
    assert migrated == {"title": "a", "tags": [], SCHEMA_VERSION_KEY: 2}


def test_a_document_runs_only_the_steps_after_its_version() -> None:
    migrated = _two_step_chain().migrate({SCHEMA_VERSION_KEY: 1, "title": "a"})
    assert migrated == {"title": "a", "tags": [], SCHEMA_VERSION_KEY: 2}


def test_a_current_document_comes_back_equal() -> None:
    doc = {SCHEMA_VERSION_KEY: 2, "title": "a", "tags": ["x"]}
    assert _two_step_chain().migrate(doc) == doc


def test_migrate_never_changes_its_input() -> None:
    doc = {"name": "a", "nested": {"k": 1}}
    _two_step_chain().migrate(doc)
    assert doc == {"name": "a", "nested": {"k": 1}}


def test_a_newer_document_is_refused_with_both_versions_named() -> None:
    with pytest.raises(SchemaVersionError, match=r"version 3.*version 2"):
        _two_step_chain().migrate({SCHEMA_VERSION_KEY: 3})


@pytest.mark.parametrize("bad", ["1", 1.0, True, -1, None])
def test_a_version_that_is_not_a_whole_number_is_refused(bad: object) -> None:
    with pytest.raises(SchemaVersionError, match="not a version number"):
        _two_step_chain().migrate({SCHEMA_VERSION_KEY: bad})


def test_a_missing_step_is_reported_not_skipped() -> None:
    chain = MigrationChain("example file", current_version=2)
    chain.register(1, _add_tags)
    assert chain.missing_steps() == [0]
    with pytest.raises(SchemaVersionError, match="no migration from it to version 1"):
        chain.migrate({})


def test_a_step_can_be_registered_only_once_and_only_inside_the_chain() -> None:
    chain = MigrationChain("example file", current_version=1)
    chain.register(0, unchanged)
    with pytest.raises(ValueError, match="already registered"):
        chain.register(0, unchanged)
    with pytest.raises(ValueError, match="between version 0 and 0"):
        chain.register(1, unchanged)


def test_a_chain_can_use_another_version_key() -> None:
    chain = MigrationChain("wire message", current_version=1, version_key="protocol")
    chain.register(0, unchanged)
    assert chain.migrate({"type": "SNAPSHOT_FULL"}) == {"type": "SNAPSHOT_FULL", "protocol": 1}


def test_stamp_and_strip_add_and_remove_only_the_version_key() -> None:
    chain = _two_step_chain()
    stamped = chain.stamp({"title": "a"})
    assert stamped == {"title": "a", SCHEMA_VERSION_KEY: 2}
    assert chain.strip(stamped) == {"title": "a"}
