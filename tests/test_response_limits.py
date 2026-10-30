"""A page fetch reads a bounded body, and only of a type the extraction can parse (SEC-2)."""

import gzip
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import pytest
from aiohttp import web

from infrastructure import NetworkClient, ResponseTooLargeError, UnsupportedContentTypeError

HTML_ONLY = ("text/html", "application/xhtml+xml")
LIMIT = 1000


@asynccontextmanager
async def serve(response_factory: Callable[[], web.Response]) -> AsyncIterator[str]:
    """A real HTTP server on 127.0.0.1 answering every GET with `response_factory()`."""

    async def handler(request: web.Request) -> web.Response:
        return response_factory()

    app = web.Application()
    app.router.add_get("/{tail:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 0).start()
    try:
        yield f"http://127.0.0.1:{runner.addresses[0][1]}/page"
    finally:
        await runner.cleanup()


async def fetch(
    url: str, content_types: tuple[str, ...] | None = HTML_ONLY, limit: int = LIMIT
) -> str:
    client = NetworkClient(allow_private_addresses=True, max_response_bytes=limit)
    try:
        body: str = await client.emit_request({"url": url, "content_types": content_types})
        return body
    finally:
        await client.close()


async def test_small_html_page_is_returned() -> None:
    async with serve(lambda: web.Response(text="<p>hi</p>", content_type="text/html")) as url:
        assert await fetch(url) == "<p>hi</p>"


async def test_declared_charset_is_used_and_bad_bytes_do_not_fail() -> None:
    body = "café".encode("latin-1") + b"\xff"
    async with serve(
        lambda: web.Response(body=body, headers={"Content-Type": "text/html; charset=latin-1"})
    ) as url:
        assert (await fetch(url)).startswith("café")


async def test_oversized_body_is_refused() -> None:
    async with serve(lambda: web.Response(text="x" * (LIMIT * 3), content_type="text/html")) as url:
        with pytest.raises(ResponseTooLargeError):
            await fetch(url)


async def test_compressed_bomb_is_stopped_after_decompression() -> None:
    bomb = gzip.compress(b"a" * (50 * 1024 * 1024))
    assert len(bomb) < LIMIT * 100  # small on the wire, huge once decompressed
    async with serve(
        lambda: web.Response(
            body=bomb, headers={"Content-Type": "text/html", "Content-Encoding": "gzip"}
        )
    ) as url:
        with pytest.raises(ResponseTooLargeError):
            await fetch(url, limit=1024 * 1024)


async def test_non_html_content_is_refused_unread() -> None:
    async with serve(lambda: web.Response(body=b"%PDF-1.7", content_type="application/pdf")) as url:
        with pytest.raises(UnsupportedContentTypeError, match="application/pdf"):
            await fetch(url)


async def test_missing_content_type_is_refused_for_pages() -> None:
    async with serve(lambda: web.Response(body=b"<p>x</p>", headers={})) as url:
        with pytest.raises(UnsupportedContentTypeError):
            await fetch(url)


async def test_any_type_is_read_when_the_caller_names_none() -> None:
    # robots.txt is plain text: its fetch names no content types.
    async with serve(lambda: web.Response(text="User-agent: *", content_type="text/plain")) as url:
        assert await fetch(url, content_types=None) == "User-agent: *"
