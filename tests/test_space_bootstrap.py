"""SpaceBootstrapper builds a blueprint's first space: seeds, target, trace order."""
import asyncio
from typing import Any

import numpy as np

from nlp import VectorSpace
from nlp.embedding_engine import HashingEmbeddingEngine
from services.space_bootstrap import SpaceBootstrapper

TOPIC = "insulin resistance and type 2 diabetes"
SEEDS = ["insulin resistance in diabetes", "metformin and glucose control"]
EXPANSION = {"llm_type": "x", "llm_model": "m", "num_descriptions": 2, "style": "balanced"}


class SeedLlm:
    async def send(self, context: object) -> dict[str, list[str]]:
        return {"descriptions": SEEDS}


class RecordingTracer:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def emit(self, event: object) -> None:
        self.log.append(type(event).__name__)


def test_seeds_and_target_reach_the_space_before_bootstrap_is_reported() -> None:
    log: list[str] = []
    adopted: dict[str, Any] = {}

    def adopt(space: VectorSpace, target_vec: np.ndarray) -> None:
        log.append("adopt")
        adopted.update(space=space, target=target_vec)

    bootstrapper = SpaceBootstrapper(
        "bp", HashingEmbeddingEngine(), SeedLlm(), EXPANSION,  # type: ignore[arg-type]
        tracer=RecordingTracer(log),  # type: ignore[arg-type]
    )
    asyncio.run(bootstrapper.build(TOPIC, adopt))

    assert log == [
        "EXP_Triggered", "EXP_PromptBuilt", "EXP_SeedsGenerated", "adopt",
        "EXP_SpaceBootstrapped",
    ]
    space = adopted["space"]
    kinds = [entry.metadata["type"] for entry in space.entries]
    assert kinds == ["seed", "seed", "target"]
    assert space.entries[-1].key == "__target__bp"
    assert np.allclose(adopted["target"], HashingEmbeddingEngine().encode(TOPIC))
    assert bootstrapper.outcomes["ok"] == 1
