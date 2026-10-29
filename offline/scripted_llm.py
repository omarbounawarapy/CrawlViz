"""The LLM double for offline runs: answers from the prompt alone."""

import json
import re
import zlib
from typing import Any

from models import LlmContext

# One answer in this many carries an expansion, so the semantic space grows
# during the crawl and later NLP scores depend on it.
EXPANSION_EVERY = 5
SCORE_RANGE = 100

_CANDIDATES = re.compile(r"CANDIDATES:\n(\[.*?\])\n", re.DOTALL)
_EXPANSION_DESCRIPTIONS = ["diabetes insulin glucose", "pancreas care"]


class ScriptedLlm:
    """Answers expansion and scoring prompts from the prompt alone.

    Each candidate's score is a checksum of its URL, so it is arbitrary but
    identical on every run and every machine.
    """

    async def send(self, context: LlmContext) -> dict[str, Any]:
        match = _CANDIDATES.search(context.get_prompt())
        if not match:
            return {"target": "pin topic", "descriptions": _EXPANSION_DESCRIPTIONS}
        urls = [candidate["url"] for candidate in json.loads(match.group(1))]
        results = []
        for url in urls:
            checksum = zlib.crc32(url.encode())
            results.append(
                {
                    "url": url,
                    "score": checksum % SCORE_RANGE,
                    "relevance_type": "direct",
                    "expansions": [f"insulin {url}"] if checksum % EXPANSION_EVERY == 0 else [],
                }
            )
        return {"results": results}
