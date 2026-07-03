import json
import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


class OpenRouterTranslator:
    """
    Translates between ScoringContext ↔ OpenRouter API format.
    """

    @staticmethod
    def translate_request(context) -> dict:
        return {
            "method": "POST",
            "url": "https://openrouter.ai/api/v1/chat/completions",
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
    def translate_response(response: Any) -> Dict:
        """
        Extract and parse the JSON payload from an OpenRouter response.
        Handles: raw dict, stringified JSON, JSON wrapped in markdown fences.
        """
        try:
            raw = response["choices"][0]["message"]["content"]

            if isinstance(raw, dict):
                return raw

            # strip markdown code fences if present
            cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
            cleaned = re.sub(r"\s*```$", "", cleaned)

            data = json.loads(cleaned)

            if not isinstance(data, dict):
                raise ValueError(f"Expected dict, got {type(data).__name__}")

            return data

        except Exception as e:
            logger.warning(
                "Failed to parse OpenRouter response: %s. Raw response: %.300s",
                e, response,
            )
            return {}