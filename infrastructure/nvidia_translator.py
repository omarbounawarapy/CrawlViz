import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class NvidiaTranslator:
    """Translates between ScoringContext/ExpansionContext and NVIDIA's NIM
    (build.nvidia.com) Chat Completions API format.

    Like OpenRouter, NVIDIA's hosted inference API is OpenAI-compatible --
    same ``Authorization: Bearer`` auth, same ``messages``/``model`` request
    body, same ``choices[0].message.content`` response shape -- so this
    translator is deliberately close to OpenAITranslator/OpenRouterTranslator.
    The only real difference is the endpoint, and that `model_information`
    here is an NVIDIA-hosted model identifier (e.g.
    ``meta/llama-3.1-70b-instruct``), not an OpenAI or OpenRouter one.
    """

    @staticmethod
    def translate_request(context) -> dict:
        return {
            "method": "POST",
            "url": "https://integrate.api.nvidia.com/v1/chat/completions",
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
        """Extract and parse the JSON payload from an NVIDIA NIM response.

        Same defensive parsing as OpenAITranslator/OpenRouterTranslator.translate_response:
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
                "Failed to parse NVIDIA response: %s. Raw response: %.300s",
                e, response,
            )
            return {}
