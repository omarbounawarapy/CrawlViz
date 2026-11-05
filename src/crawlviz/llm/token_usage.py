"""Token counts from provider responses. Each reader returns
``(input_tokens, output_tokens)`` and never raises: a response without usage
data counts as ``(0, 0)``."""

from typing import Any


def _count(source: Any, *names: str) -> int:
    for name in names:
        value = source.get(name) if isinstance(source, dict) else None
        if isinstance(value, int):
            return value
    return 0


def openai_usage(response: Any) -> tuple[int, int]:
    usage = response.get("usage") if isinstance(response, dict) else None
    return _count(usage, "prompt_tokens"), _count(usage, "completion_tokens")


def anthropic_usage(response: Any) -> tuple[int, int]:
    usage = response.get("usage") if isinstance(response, dict) else None
    return _count(usage, "input_tokens"), _count(usage, "output_tokens")


def gemini_usage(response: Any) -> tuple[int, int]:
    usage = response.get("usageMetadata") if isinstance(response, dict) else None
    return _count(usage, "promptTokenCount"), _count(usage, "candidatesTokenCount")
