"""Doubles for the outside world of a pin crawl: the LLM and the WebSocket gateway.

The web is a ``FrozenGraph`` and the embedding model is ``HashingEmbeddingEngine``;
both come from the repository, and so does the scripted LLM (``offline``). The recording
doubles are written for the pins.
"""

from typing import Any, Protocol

from models import LlmContext
from offline.scripted_llm import ScriptedLlm

__all__ = ["LlmSender", "RecordingGateway", "RecordingLlm", "ScriptedLlm"]


class LlmSender(Protocol):
    """Anything with ``send(context)``, like ``LlmHandler`` and ``CachedLlm``."""

    # Any: the LLM's answer is JSON from outside the program.
    async def send(self, context: LlmContext) -> dict[str, Any]: ...


class RecordingLlm:
    """Keeps the request body of every call, then passes the call on."""

    def __init__(self, inner: LlmSender) -> None:
        self.inner = inner
        self.requests: list[dict[str, str]] = []

    async def send(self, context: LlmContext) -> dict[str, Any]:
        self.requests.append(
            {
                "llm_type": context.get_llm_type(),
                "model": context.get_model_information(),
                "prompt": context.get_prompt(),
            }
        )
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
