"""The `pipelines.<key>` settings sections under the one-key names of ADR 6.

Each stage reads its workers and queue bound from ``pipelines.<key>``. Before ADR 6 those
keys were the old pipeline names (``requests``, ``processing``, ...); after it they are the
stage keys (``fetch``, ``extract``, ...). ``rename_pipeline_settings`` is the migration
step that moves a settings patch from the old names to the new ones. It is one source for
every format that holds a settings patch: the settings file, each saved preset and the
``runtime_config`` of a run manifest.

No chain registers it yet. ``PipelinesConfig`` still reads the old keys, so the version bump
of those formats lands in the commit that renames the model's fields.
"""

from __future__ import annotations

import copy
from typing import Final

from .versioning import Document, StoredFormatError

PIPELINES_SECTION: Final = "pipelines"

# Old section key -> ADR 6 key. `storage` and `retry` already have their ADR 6 key.
PIPELINE_SETTING_RENAMES: Final[dict[str, str]] = {
    "processing": "extract",
    "requests": "fetch",
    "scoring": "score",
    "filtering": "filter",
    "priority": "prioritize",
    "transformation": "transform",
    "debugging": "debug_log",
}


def rename_pipeline_settings(patch: Document) -> Document:
    """A copy of ``patch`` whose ``pipelines`` sections use the ADR 6 keys.

    A patch already on the new keys, or without a ``pipelines`` object, comes back equal.
    Raises ``StoredFormatError`` when one section appears under both its old and new key,
    because either value could be the one the user meant."""
    migrated = copy.deepcopy(patch)
    sections = migrated.get(PIPELINES_SECTION)
    if not isinstance(sections, dict):
        # Missing, or malformed: the settings model reports a malformed section with its path.
        return migrated
    for old_key, new_key in PIPELINE_SETTING_RENAMES.items():
        if old_key in sections and new_key in sections:
            raise StoredFormatError(
                f"{PIPELINES_SECTION}.{old_key} and {PIPELINES_SECTION}.{new_key} are the "
                f"same setting under its old and new name. Keep only "
                f"{PIPELINES_SECTION}.{new_key}."
            )
    migrated[PIPELINES_SECTION] = {
        PIPELINE_SETTING_RENAMES.get(key, key): value for key, value in sections.items()
    }
    return migrated
