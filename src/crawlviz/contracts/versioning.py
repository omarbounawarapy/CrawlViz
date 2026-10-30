"""One migration mechanism for every stored format and the wire (ADR 5).

A stored document is a plain JSON object with an integer version under one key
(``schema_version`` for files, ``protocol`` for the wire). A document without that key is
version 0, the format written before versions existed. A ``MigrationChain`` holds one pure
function per step, from version N to N + 1, and brings any older document to the current
version before it is validated. A document newer than the code is refused with a message
that names both versions, so a file written by a later CrawlViz is never half-read.

Writers stamp the current version only (``MigrationChain.stamp``); nothing is written back
on load.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any, Final

SCHEMA_VERSION_KEY: Final = "schema_version"
# The version of a document written before it carried one.
UNVERSIONED: Final = 0

# Any: stored documents are JSON objects of any shape until the format's model validates them.
Document = dict[str, Any]
Migration = Callable[[Document], Document]


class SchemaVersionError(ValueError):
    """A document's version is missing a migration, malformed or newer than this build."""


class MigrationChain:
    """The ordered migrations of one format, from version 0 to ``current_version``.

    Each step is registered once with ``register(from_version, migration)``. The migration
    receives a deep copy of the document and returns the document at ``from_version + 1``;
    the chain sets the version key itself, so a step only moves and renames fields.
    """

    def __init__(
        self, format_name: str, current_version: int, version_key: str = SCHEMA_VERSION_KEY
    ) -> None:
        if current_version < UNVERSIONED:
            raise ValueError(f"{format_name}: the current version must be 0 or more")
        self.format_name = format_name
        self.current_version = current_version
        self.version_key = version_key
        self._steps: dict[int, Migration] = {}

    def register(self, from_version: int, migration: Migration) -> Migration:
        """Add the step from ``from_version`` to the next version; returns ``migration``."""
        if not UNVERSIONED <= from_version < self.current_version:
            raise ValueError(
                f"{self.format_name}: a step must start between version {UNVERSIONED} and "
                f"{self.current_version - 1}, not {from_version}"
            )
        if from_version in self._steps:
            raise ValueError(
                f"{self.format_name}: the step from version {from_version} is already registered"
            )
        self._steps[from_version] = migration
        return migration

    def missing_steps(self) -> list[int]:
        """The start versions that have no step yet; empty when the chain is complete."""
        return [v for v in range(UNVERSIONED, self.current_version) if v not in self._steps]

    def version_of(self, document: Document) -> int:
        """The document's version: ``UNVERSIONED`` when the key is absent."""
        version = document.get(self.version_key, UNVERSIONED)
        # bool is an int subclass; `true` is not a version.
        if isinstance(version, bool) or not isinstance(version, int) or version < UNVERSIONED:
            raise SchemaVersionError(
                f"The {self.format_name} has {self.version_key} {version!r}, which is not a "
                f"version number. Set it to a whole number from {UNVERSIONED} to "
                f"{self.current_version}, or remove it if the file predates versions."
            )
        return version

    def migrate(self, document: Document) -> Document:
        """A copy of ``document`` brought to the current version, version key included.

        Raises ``SchemaVersionError`` when the document is newer than this build or a step is
        missing. The input is never changed."""
        version = self.version_of(document)
        if version > self.current_version:
            raise SchemaVersionError(
                f"The {self.format_name} is version {version}, but this CrawlViz reads "
                f"version {self.current_version} at most. Update CrawlViz to open it."
            )
        migrated = copy.deepcopy(document)
        while version < self.current_version:
            step = self._steps.get(version)
            if step is None:
                raise SchemaVersionError(
                    f"The {self.format_name} is version {version}, and this CrawlViz has no "
                    f"migration from it to version {version + 1}. Report this as a bug."
                )
            migrated = step(migrated)
            version += 1
            migrated[self.version_key] = version
        migrated[self.version_key] = self.current_version
        return migrated

    def stamp(self, document: Document) -> Document:
        """A copy of ``document`` with the current version set, ready to be written."""
        return {**document, self.version_key: self.current_version}

    def strip(self, document: Document) -> Document:
        """A copy of ``document`` without the version key, for models that do not declare it."""
        return {k: v for k, v in document.items() if k != self.version_key}


def unchanged(document: Document) -> Document:
    """The step for a version bump that only adds the version key."""
    return document
