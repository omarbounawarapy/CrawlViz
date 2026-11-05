"""The version chains of the files CrawlViz stores, and the helpers that read and write them.

Each format reads with ``load_*`` (any older version is migrated, a newer one refused) and
writes with ``dump_*`` (the current version is stamped). Version 0 is the unversioned
format written before ADR 5; version 1 is the same content with ``schema_version`` added.
Version 2 of a format that holds settings names the ``pipelines`` sections by the ADR 6
stage keys (``fetch`` where version 1 had ``requests``).

| Format | File | Version key kept after loading |
|---|---|---|
| settings | ``settings.json`` | no: the body is a ``RuntimeConfig`` patch |
| presets | ``presets.json`` | no: the body is ``{name: settings patch}`` |
| blueprint | ``templates/<name>.json`` | no: the body is a blueprint |
| run manifest | ``<export_dir>/<crawl_id>/manifest.json`` | yes: it is part of the record |
"""

from __future__ import annotations

from typing import Final

from .pipeline_settings import rename_pipeline_settings
from .versioning import (
    SCHEMA_VERSION_KEY,
    Document,
    MigrationChain,
    StoredFormatError,
    unchanged,
)

SETTINGS_FILE: Final = MigrationChain("settings file", current_version=2)
SETTINGS_FILE.register(0, unchanged)
SETTINGS_FILE.register(1, rename_pipeline_settings)

PRESETS_FILE: Final = MigrationChain("presets file", current_version=1)

# Version 1 nests the presets under one key, so a preset name can never collide with
# `schema_version` or any key a later version adds.
PRESETS_KEY: Final = "presets"


def _presets_nest_under_one_key(document: Document) -> Document:
    """Version 0 was ``{name: values}``; version 1 is ``{"presets": {name: values}}``."""
    return {PRESETS_KEY: document}


PRESETS_FILE.register(0, _presets_nest_under_one_key)

BLUEPRINT_FILE: Final = MigrationChain("blueprint", current_version=1)
BLUEPRINT_FILE.register(0, unchanged)

RUN_MANIFEST: Final = MigrationChain("run manifest", current_version=1)
RUN_MANIFEST.register(0, unchanged)

STORED_FORMATS: Final[tuple[MigrationChain, ...]] = (
    SETTINGS_FILE,
    PRESETS_FILE,
    BLUEPRINT_FILE,
    RUN_MANIFEST,
)


def load_settings_document(stored: Document) -> Document:
    """The stored settings patch at the current version, without the version key."""
    return SETTINGS_FILE.strip(SETTINGS_FILE.migrate(stored))


def dump_settings_document(patch: Document) -> Document:
    """The settings patch as it is written to ``settings.json``."""
    return SETTINGS_FILE.stamp(patch)


def load_presets_document(stored: Document) -> dict[str, Document]:
    """The saved presets by name, from a presets file of any known version."""
    # Version 0 allowed a preset named `schema_version`: its value is a settings patch, not a
    # version, and the file is version 0.
    same_named_preset = stored.get(SCHEMA_VERSION_KEY)
    if isinstance(same_named_preset, dict):
        stored = PRESETS_FILE.strip(stored)
    presets = PRESETS_FILE.migrate(stored).get(PRESETS_KEY, {})
    if not isinstance(presets, dict):
        raise StoredFormatError(
            f"The presets file holds {type(presets).__name__} under '{PRESETS_KEY}' where it "
            "needs an object of presets by name. Fix it by hand, or delete the file to start "
            "with no saved presets."
        )
    by_name: dict[str, Document] = dict(presets)
    if isinstance(same_named_preset, dict):
        by_name[SCHEMA_VERSION_KEY] = same_named_preset
    return by_name


def dump_presets_document(presets: dict[str, Document]) -> Document:
    """The saved presets as they are written to ``presets.json``."""
    return PRESETS_FILE.stamp({PRESETS_KEY: presets})


def load_blueprint_document(stored: Document) -> Document:
    """The blueprint at the current version, without the version key."""
    return BLUEPRINT_FILE.strip(BLUEPRINT_FILE.migrate(stored))


def dump_blueprint_document(blueprint: Document) -> Document:
    """The blueprint as it is written to ``templates/<name>.json``."""
    return BLUEPRINT_FILE.stamp(blueprint)


def load_run_manifest(stored: Document) -> Document:
    """The run manifest at the current version, version key included."""
    return RUN_MANIFEST.migrate(stored)


def dump_run_manifest(manifest: Document) -> Document:
    """The run manifest as it is written to ``manifest.json``."""
    return RUN_MANIFEST.stamp(manifest)
