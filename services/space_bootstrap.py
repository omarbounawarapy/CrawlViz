"""Building a blueprint's first semantic space from its target topic.

The LLM describes the topic ("expansions"); each description is embedded as
a seed vector, and the topic itself is added as the target vector. This runs
once per blueprint: later runs load the stored space (``NLPService.start``).
See docs/adr/0003-nlp-service-split.md.
"""

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np

from infrastructure import LlmHandler
from models import ExpansionContext
from nlp import BaseEmbeddingEngine, ExpansionPromptBuilder, VectorSpace
from traceability.expansion_trace_events import (
    EXP_CandidatePruned,
    EXP_PromptBuilt,
    EXP_SeedsGenerated,
    EXP_SpaceBootstrapped,
    EXP_Triggered,
)
from traceability.trace_context import get_trace, new_trace_id

from .llm_contracts import Outcomes, parse_expansion_seeds

if TYPE_CHECKING:
    from traceability.emitter import TraceEmitter

logger = logging.getLogger(__name__)

# Seed and prompt previews in trace events are cut to these lengths.
SEED_PREVIEW_CHARS = 80
PROMPT_PREVIEW_CHARS = 300

SeedVector = tuple[str, np.ndarray, dict[str, str]]


class SpaceBootstrapper:
    """Builds the first space for one blueprint.

    Args:
        blueprint_id: The blueprint whose space this is; part of every key.
        engine: Embeds the topic and the seed descriptions.
        llm_handler: Answers the expansion prompt.
        expansion_config: The blueprint's ``expansion`` section (llm_type,
            llm_model, style, num_descriptions, ...).
        tracer: Optional TraceEmitter; when None, tracing is a no-op.
    """

    def __init__(
        self,
        blueprint_id: str,
        engine: BaseEmbeddingEngine,
        llm_handler: LlmHandler,
        # The blueprint's JSON section, as loaded.
        expansion_config: dict[str, Any],
        tracer: "TraceEmitter | None" = None,
    ) -> None:
        self.blueprint_id = blueprint_id
        self.engine = engine
        self.llm_handler = llm_handler
        self.expansion_config = expansion_config
        self.llm_type: str = expansion_config["llm_type"]
        self.model_information: str = expansion_config["llm_model"]
        self.prompt_builder = ExpansionPromptBuilder()
        self.outcomes = Outcomes()
        self._tracer = tracer

    async def _emit(self, event: object) -> None:
        if self._tracer is not None:
            await self._tracer.emit(event)

    async def build(
        self, target_topic: str, adopt: Callable[[VectorSpace, np.ndarray], None]
    ) -> None:
        """Build the space and hand it, with the target vector, to `adopt`
        (which saves it) before the bootstrap is reported as done."""
        started = time.monotonic()
        trace_id, node_id = self._bootstrap_trace()

        await self._emit(EXP_Triggered(
            trace_id=trace_id,
            node_id=node_id,
            blueprint_id=self.blueprint_id,
            target_topic=target_topic,
            trigger_reason="new_blueprint",
        ))

        logger.info("Building new semantic space for '%s'", self.blueprint_id)
        space = VectorSpace(dim=self.engine.dim)
        target_vec = self.engine.encode(target_topic)

        expansions = await self.create_expansions(target_topic, self.expansion_config)
        seeds: list[str] = expansions.get("descriptions", [])
        await self._emit(EXP_SeedsGenerated(
            trace_id=trace_id,
            node_id=node_id,
            blueprint_id=self.blueprint_id,
            seed_count=len(seeds),
            seed_previews=[s[:SEED_PREVIEW_CHARS] for s in seeds],
            source="llm_expansion",
        ))

        seed_vectors = await self._encode_seeds(seeds, trace_id, node_id)
        space.add_batch(seed_vectors)
        space.add_vector(
            key=f"__target__{self.blueprint_id}",
            vector=target_vec,
            metadata={"type": "target", "text": target_topic},
        )
        adopt(space, target_vec)

        await self._emit(EXP_SpaceBootstrapped(
            trace_id=trace_id,
            node_id=node_id,
            blueprint_id=self.blueprint_id,
            vectors_added=len(seed_vectors) + 1,
            space_version=space.version,
            duration_ms=(time.monotonic() - started) * 1000,
        ))

    def _bootstrap_trace(self) -> tuple[str, str]:
        """The current trace, or a new one named after the blueprint when the
        bootstrap runs outside any trace."""
        trace_id, node_id = get_trace()
        if not trace_id:
            return new_trace_id(), f"bootstrap:{self.blueprint_id}"
        return trace_id, node_id

    async def _encode_seeds(
        self, seeds: list[str], trace_id: str, node_id: str
    ) -> list[SeedVector]:
        """One vector per description; a description that fails to embed is
        logged and reported as pruned, and the rest are kept."""
        seed_vectors: list[SeedVector] = []
        for description in seeds:
            try:
                vec = self.engine.encode(description)
                key = f"seed::{self.blueprint_id}::{hash(description)}"
                seed_vectors.append((key, vec, {"type": "seed"}))
            except Exception:
                logger.exception(
                    "Failed to encode seed description: %r", description[:SEED_PREVIEW_CHARS]
                )
                await self._emit(EXP_CandidatePruned(
                    trace_id=trace_id,
                    node_id=node_id,
                    blueprint_id=self.blueprint_id,
                    seed_preview=description[:SEED_PREVIEW_CHARS],
                    reason="error",
                    threshold=None,
                ))
        return seed_vectors

    async def create_expansions(
        self, target: str, expansion_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Ask the LLM to describe `target`. A failed request or a malformed
        answer yields no descriptions; each outcome is counted."""
        trace_id, node_id = get_trace()

        prompt = self.prompt_builder.build(target, expansion_config)

        await self._emit(EXP_PromptBuilt(
            trace_id=trace_id,
            node_id=node_id,
            blueprint_id=self.blueprint_id,
            style=expansion_config.get("style", "balanced"),
            num_descriptions=expansion_config.get("num_descriptions", 6),
            prompt_len=len(prompt),
            prompt_preview=prompt[:PROMPT_PREVIEW_CHARS],
        ))

        context = ExpansionContext(
            self.llm_type,
            self.model_information,
            prompt,
        )
        logger.debug("Sending expansion request to LLM for '%s'", target)
        try:
            raw = await self.llm_handler.send(context)
        except Exception:
            logger.exception("Expansion request failed for '%s'", target)
            self.outcomes["request_failed"] += 1
            return {"descriptions": []}
        parsed = parse_expansion_seeds(raw)
        if parsed is None:
            logger.warning("Expansion response was not an object: %.200r", raw)
            self.outcomes["malformed_response"] += 1
            return {"descriptions": []}
        self.outcomes["ok" if parsed.descriptions else "empty"] += 1
        return parsed.model_dump()
