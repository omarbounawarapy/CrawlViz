"""Token counts from provider responses.

Each reader returns ``(input_tokens, output_tokens)`` and never raises: a
response without usage data counts as ``(0, 0)``, and a count that is not a
whole non-negative number counts as 0. Input is every prompt token the model
read, output every token it generated, so the counts match what is billed:

- OpenAI-compatible (OpenAI, OpenRouter, Groq, NVIDIA, local servers):
  ``prompt_tokens`` already includes cached tokens and ``completion_tokens``
  already includes reasoning tokens.
- Anthropic: ``input_tokens`` leaves out the prompt tokens written to or read
  from the prompt cache, which are reported apart.
- Gemini: ``candidatesTokenCount`` leaves out a thinking model's reasoning,
  reported as ``thoughtsTokenCount`` and billed as output.
"""

from typing import Any

OPENAI_INPUT = ("prompt_tokens",)
OPENAI_OUTPUT = ("completion_tokens",)
ANTHROPIC_INPUT = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
ANTHROPIC_OUTPUT = ("output_tokens",)
GEMINI_INPUT = ("promptTokenCount",)
GEMINI_OUTPUT = ("candidatesTokenCount", "thoughtsTokenCount")


def _total(usage: Any, names: tuple[str, ...]) -> int:  # Any: provider JSON
    """Sum of the counts in `usage` under `names`; missing or malformed ones add 0."""
    if not isinstance(usage, dict):
        return 0
    counts = (usage.get(name) for name in names)
    # bool is an int subclass; a provider never means True as a token count.
    return sum(count for count in counts if type(count) is int and count >= 0)


def _usage(
    response: Any, block: str, input_names: tuple[str, ...], output_names: tuple[str, ...]
) -> tuple[int, int]:
    usage = response.get(block) if isinstance(response, dict) else None
    return _total(usage, input_names), _total(usage, output_names)


def openai_usage(response: Any) -> tuple[int, int]:  # Any: provider JSON
    return _usage(response, "usage", OPENAI_INPUT, OPENAI_OUTPUT)


def anthropic_usage(response: Any) -> tuple[int, int]:  # Any: provider JSON
    return _usage(response, "usage", ANTHROPIC_INPUT, ANTHROPIC_OUTPUT)


def gemini_usage(response: Any) -> tuple[int, int]:  # Any: provider JSON
    return _usage(response, "usageMetadata", GEMINI_INPUT, GEMINI_OUTPUT)
