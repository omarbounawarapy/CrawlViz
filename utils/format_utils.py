import logging
from json import loads
from typing import Any

logger = logging.getLogger(__name__)


def text_to_json(text: str) -> list[Any]:
    """Extract every top-level ``{...}`` JSON object embedded in free text.

    Used as a fallback for LLM responses that wrap JSON in prose
    instead of returning it cleanly. Matches on the first closing
    brace, so it only handles flat (non-nested) objects correctly.
    """
    try:
        items = []
        temp = ""
        capturing = False
        for char in text:
            if char == "}":
                temp += char
                capturing = False
                items.append(loads(temp))
            elif capturing:
                temp += char
            elif char == "{":
                temp = char
                capturing = True
        return items

    except Exception:
        logger.warning("Failed to extract JSON from text: %r", text)
        return []
