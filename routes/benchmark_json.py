"""Small helpers for turning benchmark numbers into JSON."""

import math
from typing import Any


def nan_to_none(value: Any) -> Any:
    """JSON has no NaN, so a NaN float becomes null; everything else passes through."""
    return None if isinstance(value, float) and math.isnan(value) else value
