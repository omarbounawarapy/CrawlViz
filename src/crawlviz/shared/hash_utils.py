import hashlib
import json
from typing import Any


def hash_item(item: Any) -> str:
    """Return a stable SHA-256 hex digest of `item`, used to deduplicate
    extracted items and as their primary key on export.
    """
    item_fp = hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()
    return item_fp
