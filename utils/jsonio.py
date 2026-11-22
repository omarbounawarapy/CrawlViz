"""Read and write JSON files, so every caller gets UTF-8 and an all-or-nothing write."""

import json
import os
from collections.abc import Callable
from typing import Any

from .atomic_write import write_text_atomic

DEFAULT_INDENT = 2


def load_json(path: str | os.PathLike[str]) -> Any:  # Any: the file's JSON is untyped.
    """Parse the JSON file at ``path``."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save_json(
    path: str | os.PathLike[str],
    data: Any,  # Any: the caller's JSON-serialisable value.
    *,
    indent: int | None = DEFAULT_INDENT,
    sort_keys: bool = False,
    default: Callable[[Any], Any] | None = None,
) -> None:
    """Replace the file at ``path`` with ``data`` as JSON, never leaving half a file."""
    write_text_atomic(path, json.dumps(data, indent=indent, sort_keys=sort_keys, default=default))
