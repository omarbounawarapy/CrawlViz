"""Extraction profiles: named sets of fields the server resolves for a blueprint.

A blueprint in profile mode stores only `profile_mode`, `profile_id` and an optional
`profile_field_checklist` in its `extraction` section. `resolve_profile_fields` turns those
into the `fields` the extractor and the exporter read, so a profile-mode blueprint extracts
the same way a manual one does.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROFILES_FILE = Path(__file__).with_name("extraction_profiles.json")


class ProfileError(ValueError):
    """A profile id or field checklist that the profile registry cannot resolve."""


def load_profiles(path: Path = PROFILES_FILE) -> dict[str, Any]:
    """Read the profile registry (profile_id to profile) from its JSON file."""
    with path.open(encoding="utf-8") as handle:
        # JSON boundary: the registry file is hand-edited data.
        profiles: dict[str, Any] = json.load(handle).get("profiles", {})
    return profiles


PROFILE_REGISTRY: dict[str, Any] = load_profiles()


def build_field_from_profile(profile_field: dict[str, Any]) -> dict[str, Any]:
    """A fully specified field dict for one field of a profile.

    Expected keys in `profile_field`: selector, type ("scalar" or "list"),
    default_transforms (list of transform steps), export_type.
    """
    return {
        "selector": profile_field["selector"],
        "type": profile_field["type"],
        "transform": list(profile_field.get("default_transforms", [])),
        "export_type": profile_field["export_type"],
    }


def resolve_profile_fields(
    profile_id: str | None, field_checklist: list[str] | None = None
) -> dict[str, Any]:
    """The extraction fields of `profile_id`, limited to `field_checklist` when it is set.

    Raises:
        ProfileError: when no profile is named, it is unknown, or the checklist names a
            field the profile does not define.
    """
    if not profile_id:
        raise ProfileError("Profile mode needs a profile_id, and none was given.")
    if profile_id not in PROFILE_REGISTRY:
        raise ProfileError(
            f"Profile {profile_id!r} not found in registry. Available: {list(PROFILE_REGISTRY)}"
        )
    all_fields: dict[str, Any] = PROFILE_REGISTRY[profile_id]["fields"]
    if field_checklist is not None:
        unknown = set(field_checklist) - set(all_fields)
        if unknown:
            raise ProfileError(
                f"Profile {profile_id!r} does not contain field(s): {sorted(unknown)}"
            )
        all_fields = {name: spec for name, spec in all_fields.items() if name in field_checklist}
    return {name: build_field_from_profile(spec) for name, spec in all_fields.items()}


def resolve_extraction_profile(extraction: dict[str, Any]) -> dict[str, Any]:
    """The `extraction` section with its fields filled in from the chosen profile.

    A section without `profile_mode` is returned as it is. In profile mode the profile's
    fields replace any `fields` the section carries, because the editor hides them.
    """
    if not extraction.get("profile_mode"):
        return extraction
    fields = resolve_profile_fields(
        extraction.get("profile_id"), extraction.get("profile_field_checklist")
    )
    return {**extraction, "fields": fields}
