"""Removes secrets from the dictionaries written into a run's ``manifest.json``.

The manifest is a plain file next to the exported run, so anything in it can be
shared with the run. Request headers may carry credentials (``Authorization``,
``Cookie``, an API key header), so their values never reach it.
"""

import re
from typing import Any

REDACTED = "[redacted]"

# Dotted path of the mapping whose values are all redacted, whatever the header is
# called: a credential can sit under any name. The names stay, so the manifest still
# shows which headers were set.
HEADER_MAPPING_PATHS = frozenset({"runtime_config.fetch.extra_headers"})

# Key names that look like they hold a credential. ``token`` must end the name so
# that counts such as ``max_tokens`` are kept.
_SECRET_KEY = re.compile(
    r"authorization|cookie|api[-_]?key|secret|passw(or)?d|token\b",
    re.IGNORECASE,
)


def redact_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """A deep copy of `manifest` with header values and secret-looking keys redacted."""
    # Any: the manifest is JSON-shaped data of unknown depth.
    return _redact_mapping(manifest, path="")


def _redact_mapping(mapping: dict[str, Any], path: str) -> dict[str, Any]:
    redact_all_values = path in HEADER_MAPPING_PATHS
    cleaned: dict[str, Any] = {}
    for key, value in mapping.items():
        child_path = f"{path}.{key}" if path else str(key)
        if redact_all_values or _SECRET_KEY.search(str(key)):
            cleaned[key] = REDACTED
        else:
            cleaned[key] = _redact_value(value, child_path)
    return cleaned


def _redact_value(value: Any, path: str) -> Any:  # Any: JSON-shaped data
    if isinstance(value, dict):
        return _redact_mapping(value, path)
    if isinstance(value, list):
        return [_redact_value(item, path) for item in value]
    return value
