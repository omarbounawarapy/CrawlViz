"""Fixtures that pin the Config page explainers to the Python implementation.

Writes crawler-ui/src/features/config/explainers/fixtures/python_cases.json
from the real ScoringPipeline.bucket_links, priority strategies, the
RequestsPipeline backoff loop, DBSCAN and the link context extractor. The
JS calculators are tested against that file; tests/test_explainer_fixtures.py
fails when the committed file no longer matches what this script produces.

    .venv/bin/python -m tools.gen_explainer_fixtures
"""

import asyncio
import json
import math
import random
from pathlib import Path
from types import SimpleNamespace

import aiohttp
import numpy as np
from multidict import CIMultiDict, CIMultiDictProxy
from sklearn.cluster import DBSCAN
from yarl import URL

import pipelines.requests_pipeline as rp
from models.links_extractor import LinkExtractor
from pipelines.requests_pipeline import RequestsPipeline
from pipelines.scoring_pipeline import ScoringPipeline
from priority import strategy as strat

ROOT = Path(__file__).resolve().parent.parent
EXPLAINERS = ROOT / "crawler-ui/src/features/config/explainers"
SAMPLE = json.loads((EXPLAINERS / "sampleData.json").read_text())
OUT = EXPLAINERS / "fixtures/python_cases.json"


class _L:
    def __init__(self, score):
        self._nlp_score = score


CASCADE_BASE = dict(
    low_threshold=0.2,
    high_threshold=0.75,
    high_score_llm_fraction=0.3,
    low_score_sample_fraction=0.1,
    high_score_random_fraction=0.25,
)


def cascade_cases() -> list[dict]:
    scores = SAMPLE["cascadeScores"]
    variants = [
        {},
        {"high_score_llm_fraction": 1.0, "low_score_sample_fraction": 0.0},
        {"high_score_llm_fraction": 0.0, "low_score_sample_fraction": 1.0},
        {"low_threshold": 0.5, "high_threshold": 0.51},
        {"percentile_bucketing": True, "low_percentile": 20, "high_percentile": 75},
        {
            "percentile_bucketing": True,
            "low_percentile": 33.3,
            "high_percentile": 66.6,
            "percentile_min_links": 60,
        },
        {"max_llm_links": 12},
        {"max_llm_links": 5, "high_score_llm_fraction": 0.7, "high_score_random_fraction": 0.5},
        {
            "percentile_bucketing": True,
            "low_percentile": 10,
            "high_percentile": 90,
            "max_llm_links": 15,
            "low_score_sample_fraction": 0.3,
        },
    ]
    cases = []
    for extra in variants:
        cfg = {**CASCADE_BASE, **extra}
        p = ScoringPipeline(None, None, None, rng=random.Random(0), **cfg)
        links = [_L(s) for s in scores]
        sampled, skipped, dropped = p.bucket_links(links)
        cases.append(
            {
                "config": cfg,
                "scores": scores,
                "expected": {
                    "toLlm": len(sampled),
                    "trusted": len(skipped),
                    "dropped": len(dropped),
                },
            }
        )
    return cases


def strategy_cases() -> list[dict]:
    cases = []
    overrides = [None, {"target_similarity": 0.9, "depth_penalty": 0.2, "novelty_injection": 0.0}]
    for name in ("aggressive", "balanced", "exploration"):
        for weights in overrides:
            for bias in ((60, 40), (100, 0), (0, 100)):
                fn = strat.get_strategy(name, weights)
                scores = []
                for link in SAMPLE["strategyLinks"]:
                    node = SimpleNamespace(get_depth=lambda d=link["depth"]: d)
                    obj = SimpleNamespace(nlp_vector=link["features"], score=link["llm"] * 100)
                    scores.append(fn(node, obj, *bias))
                cases.append(
                    {
                        "strategy": name,
                        "weights": weights,
                        "nlpBias": bias[0],
                        "llmBias": bias[1],
                        "scores": scores,
                    }
                )
    return cases


class _Broker:
    async def emit(self, event):
        pass


class _Scripted:
    def __init__(self, outcomes, log):
        self.outcomes = list(outcomes)
        self.log = log

    async def emit_request(self, params):
        kind = self.outcomes.pop(0)
        self.log.append(("request", 0.0))
        if kind == "429":
            info = aiohttp.RequestInfo(
                url=URL("https://example.test"),
                method="GET",
                headers=CIMultiDictProxy(CIMultiDict()),
                real_url=URL("https://example.test"),
            )
            raise aiohttp.ClientResponseError(info, (), status=429)
        if kind == "fail":
            raise RuntimeError("500")
        return "<html></html>"

    async def close(self):
        pass


async def _backoff_run(cfg: dict, outcomes: list[str]) -> list[float]:
    """Seconds waited before each request, driving the real worker loop."""
    log: list[tuple[str, float]] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(seconds, *a):
        log.append(("sleep", seconds))
        await real_sleep(0)

    rp.asyncio.sleep = fake_sleep
    try:
        pipe = RequestsPipeline(
            _Broker(),
            max_concurrency=1,
            fetcher=_Scripted(outcomes, log),
            jitter_max=0.0,
            min_delay=cfg["min_delay"],
            backoff_start=cfg["backoff_start"],
            max_backoff=cfg["backoff_max"],
            backoff_growth=cfg["backoff_growth"],
            backoff_success_decay=cfg["backoff_success_decay"],
            backoff_failure_decay=cfg["backoff_failure_decay"],
        )
        from models import Domain, Node

        domain = Domain("d", "https://example.test", ".//a")
        for i in range(len(outcomes)):
            await pipe.queue.put(
                Node(i, url=f"https://example.test/{i}", domain=domain, priority=100 - i)
            )
        task = asyncio.create_task(pipe.start())
        for _ in range(10_000):
            if not pipe.network_client.outcomes or task.done():
                break
            await real_sleep(0)
        if task.done():
            task.result()
        await real_sleep(0.01)
        await pipe.stop()
        await task
    finally:
        rp.asyncio.sleep = real_sleep
    # The wait before each request: the sleep logged just ahead of it, else none.
    delays, pending = [], 0.0
    for kind, seconds in log:
        if kind == "sleep":
            pending = seconds
        else:
            delays.append(pending)
            pending = 0.0
    return delays


def backoff_cases() -> list[dict]:
    base = dict(
        min_delay=1.0,
        backoff_start=1.0,
        backoff_max=10.0,
        backoff_growth=2.0,
        backoff_success_decay=0.5,
        backoff_failure_decay=0.5,
    )
    scripts = [
        ("ok",) * 4 + ("429",) * 5 + ("ok",) * 6,
        ("429", "ok", "429", "fail", "fail", "ok", "429", "429", "429", "429", "429", "ok"),
    ]
    variants = [
        {},
        {"backoff_growth": 3.0, "backoff_max": 20.0, "min_delay": 0.5},
        {"backoff_success_decay": 0.0, "backoff_start": 2.5},
    ]
    cases = []
    for extra in variants:
        for script in scripts:
            cfg = {**base, **extra}
            delays = asyncio.run(_backoff_run(cfg, list(script)))
            # The fake request takes no time, so each wait is min_delay + backoff,
            # and the very first request has none (nothing came before it).
            cases.append(
                {"config": cfg, "outcomes": list(script), "delays": [round(d, 2) for d in delays]}
            )
    return cases


def cluster_cases() -> list[dict]:
    angles = SAMPLE["cluster"]["angles"]
    mat = np.array([[math.cos(math.radians(a)), math.sin(math.radians(a))] for a in angles])
    cases = []
    for eps in (0.002, 0.01, 0.05, 0.3, 0.8):
        for ms in (1, 2, 3):
            labels = DBSCAN(eps=eps, min_samples=ms, metric="cosine").fit_predict(mat)
            cases.append({"eps": eps, "minSamples": ms, "labels": [int(x) for x in labels]})
    return cases


def context_cases() -> list[dict]:
    text, anchor = SAMPLE["context"]["text"], SAMPLE["context"]["anchor"]
    return [
        {"limit": n, "context": LinkExtractor._extract_sentence(text[:n], anchor)}
        for n in (1, 20, 60, 100, 140, 160, 200, 400)
    ]


def build() -> dict:
    return {
        "cascade": cascade_cases(),
        "strategy": strategy_cases(),
        "backoff": backoff_cases(),
        "cluster": cluster_cases(),
        "context": context_cases(),
    }


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=1) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
