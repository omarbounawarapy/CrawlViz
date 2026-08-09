import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class GeminiTranslator:
    """Translates between ScoringContext/ExpansionContext and Google's
    Gemini generateContent API format.

    This is the most structurally different of the four translators, which
    is exactly why the translation belongs here and nowhere else in the
    system:

    - The model identifier is part of the URL path
      (``/models/{model}:generateContent``), not a body field.
    - The API key goes in an ``x-goog-api-key`` header rather than an
      Authorization header (Gemini also supports the key as a ``?key=``
      query parameter, but a header keeps it out of URLs that might end
      up in access logs).
    - The request body uses ``contents`` / ``parts``, not ``messages``.
    - The response is nested under
      ``candidates[0].content.parts[0].text``, not ``choices``.

    None of this leaks past ``translate_response``: callers still get back
    the same shape (a plain parsed dict) every other translator returns.
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    @staticmethod
    def translate_request(context) -> dict:
        model = context.get_model_information()
        return {
            "method": "POST",
            "url": f"{GeminiTranslator.BASE_URL}/{model}:generateContent",
            "headers": {
                "x-goog-api-key": context.get_key(),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            "data": {
                "contents": [
                    {"parts": [{"text": context.get_prompt()}]}
                ],
            },
        }

    @staticmethod
    def translate_response(response: Any) -> dict:
        """Extract and parse the JSON payload from a Gemini response.

        Concatenates every text part of the first candidate (a response is
        occasionally split across multiple parts), then applies the same
        defensive fence-stripping/JSON-parsing as the other translators.
        Never raises -- a malformed response, an empty ``candidates`` list
        (e.g. a safety-filtered prompt), or an unexpected shape all yield
        an empty dict rather than crashing the pipeline that's scoring it.
        """
        try:
            parts = response["candidates"][0]["content"]["parts"]
            raw = "".join(part.get("text", "") for part in parts if isinstance(part, dict))

            cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
            cleaned = re.sub(r"\s*```$", "", cleaned)

            data = json.loads(cleaned)

            if not isinstance(data, dict):
                raise ValueError(f"Expected dict, got {type(data).__name__}")

            return data

        except Exception as e:
            logger.warning(
                "Failed to parse Gemini response: %s. Raw response: %.300s",
                e, response,
            )
            return {}
