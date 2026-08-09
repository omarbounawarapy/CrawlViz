import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class OpenAITranslator:
    """Translates between ScoringContext/ExpansionContext and the OpenAI
    Chat Completions API format.

    OpenRouter's API is itself OpenAI-compatible, so this translator's
    request and response shapes are deliberately close to
    OpenRouterTranslator's -- the only real differences are the endpoint
    and the fact that a plain OpenAI key (not an OpenRouter key) goes in
    the Authorization header.
    """

    @staticmethod
    def translate_request(context) -> dict:
        return {
            "method": "POST",
            "url": "https://api.openai.com/v1/chat/completions",
            "headers": {
                "Authorization": f"Bearer {context.get_key()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            "data": {
                "model": context.get_model_information(),
                "messages": [
                    {"role": "user", "content": context.get_prompt()}
                ],
            },
        }

    @staticmethod
    def translate_response(response: Any) -> dict:
        """Extract and parse the JSON payload from an OpenAI response.

        Same defensive parsing as OpenRouterTranslator.translate_response:
        handles a raw dict, stringified JSON, or JSON wrapped in markdown
        fences, and never raises -- a malformed LLM response yields an
        empty dict rather than crashing the pipeline that's scoring it.
        """
        try:
            raw = response["choices"][0]["message"]["content"]

            if isinstance(raw, dict):
                return raw

            cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
            cleaned = re.sub(r"\s*```$", "", cleaned)

            data = json.loads(cleaned)

            if not isinstance(data, dict):
                raise ValueError(f"Expected dict, got {type(data).__name__}")

            return data

        except Exception as e:
            logger.warning(
                "Failed to parse OpenAI response: %s. Raw response: %.300s",
                e, response,
            )
            return {}
