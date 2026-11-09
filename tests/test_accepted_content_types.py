"""The content types a page fetch accepts come from the fetch settings, not from the pipeline."""

import asyncio
from typing import Any

import pytest
from pydantic import ValidationError

from config import parse_content_types
from config.runtime_config import FetchConfig, default_runtime_config
from core.event_broker import EventBroker
from models import Domain, Node
from pipelines import RequestsPipeline

BASE_URL = "https://content.test"


def test_a_list_is_split_lowercased_and_trimmed() -> None:
    assert parse_content_types("Text/HTML ,  text/plain,") == ("text/html", "text/plain")


@pytest.mark.parametrize("text", ["", " , ", "html", "text/", "/html", "text/html/extra"])
def test_a_list_with_no_valid_type_is_refused_in_plain_words(text: str) -> None:
    with pytest.raises(ValueError, match="content type"):
        parse_content_types(text)


def test_the_default_setting_accepts_html_and_xhtml() -> None:
    types = parse_content_types(default_runtime_config().fetch.accepted_content_types)

    assert types == ("text/html", "application/xhtml+xml")


def test_the_setting_rejects_an_entry_that_is_not_a_content_type() -> None:
    with pytest.raises(ValidationError, match="not a content type"):
        FetchConfig(accepted_content_types="text/html, nonsense")


class RecordingFetcher:
    def __init__(self) -> None:
        self.params: list[dict[str, Any]] = []

    async def emit_request(self, params: dict[str, Any]) -> str:
        self.params.append(params)
        return "<html></html>"

    async def close(self) -> None:
        pass


async def fetch_one_page(pipeline: RequestsPipeline, fetcher: RecordingFetcher) -> dict[str, Any]:
    domain = Domain("content", BASE_URL, ".//a")
    await pipeline.queue.put(Node(1, url=f"{BASE_URL}/page", domain=domain, priority=1.0))
    task = asyncio.create_task(pipeline.start())
    try:
        for _ in range(100):
            if fetcher.params:
                break
            await asyncio.sleep(0.02)
    finally:
        await pipeline.stop()
        await asyncio.wait_for(task, 2.0)
    return fetcher.params[0]


async def test_the_pipeline_asks_for_the_configured_types() -> None:
    fetcher = RecordingFetcher()
    pipeline = RequestsPipeline(
        EventBroker(),
        max_concurrency=1,
        fetcher=fetcher,
        min_delay=0,
        content_types=("text/plain",),
    )

    params = await fetch_one_page(pipeline, fetcher)

    assert params["content_types"] == ("text/plain",)


async def test_the_pipeline_defaults_to_the_default_setting() -> None:
    fetcher = RecordingFetcher()
    pipeline = RequestsPipeline(EventBroker(), max_concurrency=1, fetcher=fetcher, min_delay=0)

    params = await fetch_one_page(pipeline, fetcher)

    assert params["content_types"] == ("text/html", "application/xhtml+xml")
