"""An LLM call failure is traced to disk and the UI, so its trace event names the
exception class and HTTP status and never carries the request URL or headers."""

from dataclasses import asdict
from typing import Any

import aiohttp
import pytest
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from traceability.traced_llm_handler import TracedLlmHandler

FAKE_KEY = "FAKEKEY-0123456789"
SECRET_URL = f"https://user:hunter2@api.example/v1/models?alt=sse&key={FAKE_KEY}"


def _client_response_error() -> aiohttp.ClientResponseError:
    url = URL(SECRET_URL)
    headers = CIMultiDictProxy(
        CIMultiDict({"Authorization": f"Bearer {FAKE_KEY}", "x-goog-api-key": FAKE_KEY})
    )
    info = aiohttp.RequestInfo(url, "POST", headers, url)
    return aiohttp.ClientResponseError(info, (), status=401, message="Unauthorized")


class _RecordingTracer:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def emit(self, event: Any) -> None:
        self.events.append(event)

    def dumped(self) -> str:
        return repr([asdict(event) for event in self.events])


class _Context:
    def get_scoring_type(self) -> str:
        return "link_scoring"

    def get_model_information(self) -> str:
        return "model-x"

    def get_prompt(self) -> str:
        return "score these links"


class _FailingLlm:
    async def send(self, context: Any) -> dict[str, Any]:
        raise _client_response_error()


@pytest.mark.asyncio
async def test_llm_failure_records_class_and_status_not_the_exception_text() -> None:
    tracer = _RecordingTracer()
    handler = TracedLlmHandler(_FailingLlm(), tracer)  # type: ignore[arg-type]

    with pytest.raises(aiohttp.ClientResponseError):
        await handler.send(_Context())

    failed = tracer.events[-1]
    assert failed.error_type == "ClientResponseError"
    assert failed.error_message == "ClientResponseError (HTTP 401)"
    assert FAKE_KEY not in tracer.dumped()
    assert "hunter2" not in tracer.dumped()
