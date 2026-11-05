from dataclasses import dataclass
from typing import Literal

BASE_PROMPT = """
You are a semantic feature generation engine for NLP retrieval systems.

You generate structured representations of a target concept for embedding-based search.

You do NOT generate explanations, stories, or general knowledge content.
"""
STYLE_BLOCKS = {
    "concise": "Focus on minimal, high-information semantic statements.",
    "balanced": "Balance definition, function, and context.",
    "rich": "Cover multiple semantic perspectives while remaining concise.",
}
OUTPUT_SCHEMA_BLOCK = """
Return ONLY valid JSON:

{
  "target": "<string>",
  "descriptions": ["<string>", "..."]
}
"""
CONSTRAINTS_BLOCK = """
RULES:
- Each description: {max_sentences} sentence(s) max
- Each must express a different semantic facet
- No repetition
- No commentary or extra keys
- Must be valid JSON
"""
FACET_BLOCK = """
Cover diverse semantic facets such as:
definition, mechanisms, applications, usage context, related systems, real-world relevance
"""

StyleMode = Literal["concise", "balanced", "rich"]


@dataclass
class ExpansionConfig:
    num_descriptions: int = 6
    style: StyleMode = "balanced"
    max_sentences: int = 2


class ExpansionPromptBuilder:
    """Builds the prompt used to generate semantic expansions for a topic."""

    def build(self, topic: str, config: "ExpansionConfig | dict | None" = None) -> str:
        if config is None:
            config = ExpansionConfig()
        elif isinstance(config, dict):
            defaults = ExpansionConfig()
            config = ExpansionConfig(
                num_descriptions=config.get("num_descriptions", defaults.num_descriptions),
                style=config.get("style", defaults.style),
                max_sentences=config.get("max_sentences", defaults.max_sentences),
            )

        return "\n\n".join(
            [
                BASE_PROMPT,
                f"TASK:\nGenerate {config.num_descriptions} semantic descriptions for:\n{topic}",
                f"STYLE:\n{STYLE_BLOCKS[config.style]}",
                CONSTRAINTS_BLOCK.format(max_sentences=config.max_sentences),
                FACET_BLOCK,
                OUTPUT_SCHEMA_BLOCK,
            ]
        )
