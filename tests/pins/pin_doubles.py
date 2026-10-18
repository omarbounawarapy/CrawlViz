"""Doubles for the outside world of a pin crawl: the LLM and the WebSocket gateway.

The web is a ``FrozenGraph`` and the embedding model is ``HashingEmbeddingEngine``;
both come from the repository. These two are written for the pins.
"""
import json
import re
import zlib
from typing import Any, Protocol

from models import LlmContext

# One answer in this many carries an expansion, so the semantic space grows
# during the crawl and later NLP scores depend on it.
EXPANSION_EVERY = 5
SCORE_RANGE = 100

_CANDIDATES = re.compile(r"CANDIDATES:\n(\[.*?\])\n", re.DOTALL)
_EXPANSION_DESCRIPTIONS = ["diabetes insulin glucose", "pancreas care"]


class LlmSender(Protocol):
    """Anything with ``send(context)``, like ``LlmHandler`` and ``CachedLlm``."""

    # Any: the LLM's answer is JSON from outside the program.
    async def send(self, context: LlmContext) -> dict[str, Any]: ...


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
            results.append({
                "url": url,
                "score": checksum % SCORE_RANGE,
                "relevance_type": "direct",
                "expansions": [f"insulin {url}"] if checksum % EXPANSION_EVERY == 0 else [],
            })
        return {"results": results}


class RecordingLlm:
    """Keeps the request body of every call, then passes the call on."""

    def __init__(self, inner: LlmSender) -> None:
        self.inner = inner
        self.requests: list[dict[str, str]] = []

    async def send(self, context: LlmContext) -> dict[str, Any]:
        self.requests.append({
            "llm_type": context.get_llm_type(),
            "model": context.get_model_information(),
            "prompt": context.get_prompt(),
        })
        return await self.inner.send(context)


class RecordingGateway:
    """Stands in for the WebSocket gateway: keeps what would have been sent."""

    def __init__(self) -> None:
        # Any: UI messages are JSON-shaped dicts (docs/crawl_messages.ts).
        self.messages: list[dict[str, Any]] = []

    async def broadcast(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    async def stop(self) -> None:
        pass
