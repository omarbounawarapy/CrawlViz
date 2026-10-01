"""NLPService end to end with the hashing embedding engine: no MiniLM, no LLM, no network."""
import asyncio
from types import SimpleNamespace

import pytest

from models.link import Link
from nlp.embedding_engine import HashingEmbeddingEngine, create_embedding_engine
from services.nlp_service import NLPService

TOPIC = "insulin resistance and type 2 diabetes treatment"
SEEDS = [
    "insulin resistance in type 2 diabetes",
    "metformin diabetes treatment and glucose control",
    "pancreas insulin secretion and blood glucose",
    "diabetes diet exercise and insulin sensitivity",
]


class SeedLlm:
    async def send(self, context):
        import json
        return json.dumps({"descriptions": SEEDS})


def make(tmp_path, engine=None, **kw):
    return NLPService(
        blueprint_id="bp",
        target_topic=TOPIC,
        llm_handler=SeedLlm(),
        expansion_config={"llm_type": "x", "llm_model": "m", "num_descriptions": 4, "style": "balanced"},
        store_base_dir=str(tmp_path / "space"),
        engine=engine or HashingEmbeddingEngine(),
        **kw,
    )


def run(coro):
    return asyncio.run(coro)


def test_engine_is_deterministic_and_shares_words():
    e = HashingEmbeddingEngine()
    a, b, c = e.encode(["insulin diabetes", "insulin diabetes", "football league"])
    assert (a == b).all() and float(a @ c) == 0.0
    assert e.encode("x").shape == (e.dim,)
    assert create_embedding_engine("hashing", dim=16).dim == 16


def test_relevant_link_outscores_irrelevant_link(tmp_path):
    svc = make(tmp_path)

    async def go():
        await svc.start()
        links = [
            Link("http://s/a", "insulin resistance in diabetes", "how diabetes treatment targets insulin"),
            Link("http://s/b", "football league table", "match results and transfers"),
        ]
        parent = SimpleNamespace(content="<p>diabetes and insulin treatment</p>")
        return await svc.score_links(links, parent)

    good, bad = run(go())
    assert good._nlp_score > bad._nlp_score
    assert good.nlp_vector and bad.nlp_vector


def test_expansions_reach_the_space_only_after_flush(tmp_path):
    svc = make(tmp_path)

    async def go():
        await svc.start()
        before = len(svc.space)
        link = Link("http://s/a", "a", "b")
        link.expansions = ["glucose metabolism", "beta cell function"]
        await svc.update_space([link])
        assert len(svc.space) == before  # space is stable until flushed
        svc.flush_buffer()
        return before

    before = run(go())
    assert len(svc.space) == before + 2


def test_space_built_with_another_model_fails_loudly(tmp_path):
    run(make(tmp_path, HashingEmbeddingEngine(dim=64)).start())  # persists a 64-d space
    other = make(tmp_path, HashingEmbeddingEngine(dim=32))
    with pytest.raises(ValueError, match="different model"):
        run(other.start())
