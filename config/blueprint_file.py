"""Read and write blueprint files at the current stored-format version.

Every place that touches ``templates/<name>.json`` goes through these two functions, so a
blueprint is migrated on the way in and stamped with ``schema_version`` on the way out.
"""

from __future__ import annotations

import os
from typing import Any

from crawlviz.contracts import dump_blueprint_document, load_blueprint_document
from crawlviz.shared import load_json, save_json


def read_blueprint_document(stored: Any) -> Any:  # Any: a blueprint file is untyped JSON.
    """The blueprint at the current version, without ``schema_version``.

    Raises ``SchemaVersionError`` when the version is newer than this build or malformed. A
    value that is not a JSON object is returned as it is, so ``validate_blueprint`` reports it
    with the same message as before."""
    if not isinstance(stored, dict):
        return stored
    return load_blueprint_document(stored)


def load_blueprint_file(path: str | os.PathLike[str]) -> Any:  # Any: see above.
    """The blueprint stored at ``path``, at the current version."""
    return read_blueprint_document(load_json(path))


def save_blueprint_file(path: str | os.PathLike[str], blueprint: dict[str, Any]) -> None:
    """Replace the blueprint at ``path`` with ``blueprint`` stamped with the current version."""
    save_json(path, dump_blueprint_document(blueprint))
