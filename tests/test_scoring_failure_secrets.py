"""A scoring failure event reaches the UI, so it must not carry the failed request's
URL, key or headers (SEC-3)."""

import asyncio
from typing import Any

import aiohttp
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from events import ScoringFailedEvent
from pipelines.scoring_pipeline import ScoringPipeline

FAKE_KEY = "FAKEKEY-0123456789"


class _Broker:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def emit(self, event: Any) -> None:
        self.events.append(event)


class _Node:
    def __init__(self) -> None:
        self.ready: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self.ready.set_result(True)

    def get_id(self) -> int:
        return 7

    def get_links(self) -> list[object]:
        return [object()]


class _FailingNlp:
    async def score_links(self, links: Any, parent: Any) -> None:
        url = URL(f"https://user:hunter2@api.example/v1?key={FAKE_KEY}")
        headers = CIMultiDictProxy(CIMultiDict({"x-goog-api-key": FAKE_KEY}))
        info = aiohttp.RequestInfo(url, "POST", headers, url)
        raise aiohttp.ClientResponseError(info, (), status=429, message="Too Many Requests")


async def test_scoring_failure_event_carries_class_and_status_only() -> None:
    broker = _Broker()
    pipeline = ScoringPipeline(
        scoring_service=object(),  # type: ignore[arg-type]
        nlp_service=_FailingNlp(),  # type: ignore[arg-type]
        event_broker=broker,
        low_threshold=0.2,
        high_threshold=0.8,
        high_score_llm_fraction=1.0,
        low_score_sample_fraction=0.0,
        high_score_random_fraction=0.0,
    )

    await pipeline._process(_Node(), worker_id=0)

    failed = [e for e in broker.events if isinstance(e, ScoringFailedEvent)]
    assert len(failed) == 1
    assert failed[0].error_type == "ClientResponseError"
    assert failed[0].error_message == "ClientResponseError (HTTP 429)"
    assert FAKE_KEY not in failed[0].error_message
