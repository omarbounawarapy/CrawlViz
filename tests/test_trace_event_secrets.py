"""Trace events and failure events are written to disk and sent to the UI, so no
credential, URL query or request header may be in them (SEC-3)."""

from dataclasses import asdict
from typing import Any

import aiohttp
import pytest
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from traceability.traced_network_client import TracedNetworkClient

FAKE_KEY = "FAKEKEY-0123456789"
SECRET_URL = f"https://user:hunter2@api.example/v1/models?alt=sse&key={FAKE_KEY}"


def _client_response_error() -> aiohttp.ClientResponseError:
    url = URL(SECRET_URL)
    headers = CIMultiDictProxy(CIMultiDict({"x-goog-api-key": FAKE_KEY}))
    info = aiohttp.RequestInfo(url, "POST", headers, url)
    return aiohttp.ClientResponseError(info, (), status=401, message="Unauthorized")


class _RecordingTracer:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def emit(self, event: Any) -> None:
        self.events.append(event)

    def dumped(self) -> str:
        return repr([asdict(event) for event in self.events])


class _FailingClient:
    async def emit_request(self, params: dict[str, Any]) -> Any:
        raise _client_response_error()

    async def close(self) -> None:
        return None


class _WorkingClient:
    async def emit_request(self, params: dict[str, Any]) -> Any:
        return "ok"

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_network_trace_records_a_url_without_user_info_or_query() -> None:
    tracer = _RecordingTracer()
    client = TracedNetworkClient(_WorkingClient(), tracer)  # type: ignore[arg-type]

    await client.emit_request({"method": "POST", "url": SECRET_URL, "headers": {}})

    created = tracer.events[0]
    assert created.url == "https://api.example/v1/models"
    assert FAKE_KEY not in tracer.dumped()
    assert "hunter2" not in tracer.dumped()


@pytest.mark.asyncio
async def test_network_failure_records_class_and_status_not_the_exception_text() -> None:
    tracer = _RecordingTracer()
    client = TracedNetworkClient(_FailingClient(), tracer)  # type: ignore[arg-type]

    with pytest.raises(aiohttp.ClientResponseError):
        await client.emit_request({"method": "POST", "url": SECRET_URL, "headers": {}})

    failed = tracer.events[-1]
    assert failed.error_message == "ClientResponseError (HTTP 401)"
    assert failed.status_code == 401
    assert FAKE_KEY not in tracer.dumped()
    assert "hunter2" not in tracer.dumped()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Authorization": "Bearer x"}, True),
        ({"x-api-key": "x"}, True),
        ({"x-goog-api-key": "x"}, True),
        ({"X-Auth-Token": "x"}, True),
        ({"Accept": "application/json"}, False),
    ],
)
async def test_auth_header_flag_covers_every_credential_header(
    headers: dict[str, str], expected: bool
) -> None:
    tracer = _RecordingTracer()
    client = TracedNetworkClient(_WorkingClient(), tracer)  # type: ignore[arg-type]

    params = {"method": "POST", "url": "https://api.example/v1", "headers": headers}
    await client.emit_request(params)

    assert tracer.events[0].has_auth_header is expected
