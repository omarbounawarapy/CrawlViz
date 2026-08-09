import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class AnthropicTranslator:
    """Translates between ScoringContext/ExpansionContext and Anthropic's
    Messages API format.

    Two structural differences from OpenRouterTranslator/OpenAITranslator
    that this translator exists specifically to absorb, so nothing above
    it (ScoringService, NLPService, ResultMapper) has to know about them:

    - Auth is an ``x-api-key`` header plus a required ``anthropic-version``
      header, not ``Authorization: Bearer``.
    - ``max_tokens`` is a required request field with no server-side
      default (unlike OpenAI-shaped APIs, where omitting it is valid).
      CrawlViz's own contexts don't carry a token budget, so this
      translator supplies one fixed default sized for a batched scoring
      or topic-expansion response.
    - The response body is ``content``: a list of typed content blocks,
      not a single ``choices[0].message.content`` string.
    """

    ANTHROPIC_VERSION = "2023-06-01"
    DEFAULT_MAX_TOKENS = 4096

    @staticmethod
    def translate_request(context) -> dict:
        return {
            "method": "POST",
            "url": "https://api.anthropic.com/v1/messages",
            "headers": {
                "x-api-key": context.get_key(),
                "anthropic-version": AnthropicTranslator.ANTHROPIC_VERSION,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            "data": {
                "model": context.get_model_information(),
                "max_tokens": AnthropicTranslator.DEFAULT_MAX_TOKENS,
                "messages": [
                    {"role": "user", "content": context.get_prompt()}
                ],
            },
        }

    @staticmethod
    def translate_response(response: Any) -> dict:
        """Extract and parse the JSON payload from an Anthropic response.

        ``response["content"]`` is a list of content blocks (typically one,
        but a model can split its answer across several); this joins the
        text of every ``type == "text"`` block before parsing, then applies
        the same defensive fence-stripping/JSON-parsing as the other
        translators. Never raises -- a malformed response yields an empty
        dict rather than crashing the pipeline that's scoring it.
        """
        try:
            blocks = response["content"]
            raw = "".join(
                block.get("text", "")
                for block in blocks
                if isinstance(block, dict) and block.get("type") == "text"
            )

            cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
            cleaned = re.sub(r"\s*```$", "", cleaned)

            data = json.loads(cleaned)

            if not isinstance(data, dict):
                raise ValueError(f"Expected dict, got {type(data).__name__}")

            return data

        except Exception as e:
            logger.warning(
                "Failed to parse Anthropic response: %s. Raw response: %.300s",
                e, response,
            )
            return {}
