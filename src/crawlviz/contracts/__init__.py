"""Versioned contracts for the files CrawlViz stores.

Every stored file carries a ``schema_version``, and one migration chain per format brings
an older file to the current version when it is loaded.
"""

from .stored_formats import (
    STORED_FORMATS,
    StoredFormatError,
    dump_blueprint_document,
    dump_presets_document,
    dump_run_manifest,
    dump_settings_document,
    load_blueprint_document,
    load_presets_document,
    load_run_manifest,
    load_settings_document,
)
from .versioning import (
    SCHEMA_VERSION_KEY,
    UNVERSIONED,
    Document,
    Migration,
    MigrationChain,
    SchemaVersionError,
    unchanged,
)

__all__ = [
    "SCHEMA_VERSION_KEY",
    "STORED_FORMATS",
    "UNVERSIONED",
    "Document",
    "Migration",
    "MigrationChain",
    "SchemaVersionError",
    "StoredFormatError",
    "dump_blueprint_document",
    "dump_presets_document",
    "dump_run_manifest",
    "dump_settings_document",
    "load_blueprint_document",
    "load_presets_document",
    "load_run_manifest",
    "load_settings_document",
    "unchanged",
]
