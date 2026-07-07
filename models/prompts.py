import json
from typing import Any

# =========================================================
# SYSTEM PROMPT
# =========================================================

SCORING_SYSTEM_PROMPT = """
You are a semantic relevance scoring engine for a focused web crawler.

Your job is to evaluate candidate links and assign:
- a relevance score (0 to 100)
- a relevance type
- optional semantic expansions

Return ONLY valid JSON.
No markdown.
No explanation outside JSON.
""".strip()

# =========================================================
# SCORING STRATEGIES (SOFT BIAS ONLY)
# =========================================================
# Kept in sync by hand with ALLOWED_STRATEGIES in
# routes/blueprint_translator.py -- see that module's docstring.

STRATEGIES: dict[str, dict[str, str]] = {
    "TOPICAL": {
        "context": (
            "Focus on direct semantic relevance to the target topic. "
            "Penalize navigation pages."
        )
    },
    "PATHFINDING": {
        "context": (
            "Prefer links that are useful intermediate steps toward reaching the target topic."
        )
    },
    "EXPLORATION": {
        "context": "Prefer semantically diverse links to broaden coverage."
    },
    "GOAL_ORIENTED": {
        "context": "Prefer links that directly help achieve the target objective."
    },
    "DENSITY_FOCUSED": {
        "context": "Prefer content-rich links such as definitions and explanations."
    },
    "UNCERTAINTY_BIASED": {
        "context": "Prefer ambiguous links that may reveal new semantic areas."
    },
}


class PromptBuilder:
    """Builds the system and user prompts sent to the scoring LLM.

    Args:
        target_topic: The crawl's target topic, restated in every prompt.
        strategy: One of the keys in `STRATEGIES`, biasing how candidates
            are scored.

    Raises:
        ValueError: If `strategy` is not a key in `STRATEGIES`.
    """

    def __init__(self, target_topic: str, strategy: str = "TOPICAL"):
        if strategy not in STRATEGIES:
            raise ValueError(f"Unknown scoring strategy: {strategy!r}")

        self.target_topic = target_topic
        self.strategy = strategy

    def build_system_prompt(self) -> str:
        return SCORING_SYSTEM_PROMPT

    def build_prompt(self, candidates: list[Any]) -> str:
        """Assemble the full user prompt for one batch of candidate links."""
        strategy_cfg = STRATEGIES[self.strategy]
        candidate_dicts = [c.to_dict() for c in candidates]

        candidates_json = json.dumps(candidate_dicts, ensure_ascii=False)

        task_block = """
TASK:
Score each candidate URL independently from 0 to 100 based on relevance to target_topic.
""".strip()

        context_block = f"""
CONTEXT:
target_topic: {self.target_topic}
strategy: {self.strategy}
strategy_context: {strategy_cfg["context"]}
""".strip()

        candidates_block = f"""
CANDIDATES:
{candidates_json}
""".strip()

        rules_block = """
RULES:
- Each candidate URL is independent
- Use strategy_context as soft bias only
- Score range: integer 0–100
- Assign exactly one relevance_type:
  direct | partial | irrelevant | ambiguous
- Generate 2–4 semantic expansions per link
- Expansions must be conceptual, not copied text
""".strip()

        output_block = """
OUTPUT FORMAT (STRICT JSON ONLY):
{
  "results": [
    {
      "url": "string",
      "score": 0,
      "relevance_type": "direct | partial | irrelevant | ambiguous",
      "expansions": ["string", "string"]
    }
  ]
}
""".strip()

        constraints_block = """
CONSTRAINTS:
- Output ONLY valid JSON
- No markdown
- No explanation
- No extra keys
- No trailing commas
""".strip()

        return "\n\n".join([
            self.build_system_prompt(),
            task_block,
            context_block,
            candidates_block,
            rules_block,
            output_block,
            constraints_block,
        ])

    def set_strategy(self, strategy: str) -> None:
        if strategy not in STRATEGIES:
            raise ValueError(f"Unknown scoring strategy: {strategy!r}")
        self.strategy = strategy
