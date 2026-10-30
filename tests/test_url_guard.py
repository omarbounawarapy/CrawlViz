"""Page fetches refuse private, loopback, link-local and metadata addresses (SEC-2)."""

from contextlib import asynccontextmanager

import pytest
from aiohttp import web
from yarl import URL

from infrastructure import BlockedAddressError, NetworkClient, TooManyRedirectsError
from infrastructure.network_client import MAX_REDIRECTS, GetRequestStrategy
from infrastructure.url_guard import PublicAddressResolver, ensure_public_url, is_blocked_address

PUBLIC_URL = "http://93.184.216.34/start"  # a public literal, so no DNS lookup is needed


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.3.4",
        "192.168.1.1",
        "169.254.169.254",  # cloud metadata
        "100.100.100.200",  # Alibaba metadata, carrier-grade NAT range
        "0.0.0.0",
        "::1",
        "fe80::1",
        "fd00:ec2::254",  # AWS IPv6 metadata
        "::ffff:127.0.0.1",  # IPv4 loopback wrapped in IPv6
        "224.0.0.1",
    ],
)
def test_non_public_addresses_are_blocked(address):
    assert is_blocked_address(address)


@pytest.mark.parametrize("address", ["93.184.216.34", "8.8.8.8", "2606:2800:220:1::1"])
def test_public_addresses_are_allowed(address):
    assert not is_blocked_address(address)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/run",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.1.2.3/admin",
        "file:///etc/passwd",
        "ftp://93.184.216.34/file",
        "http:///nohost",
    ],
)
def test_unsafe_urls_are_rejected(url):
    with pytest.raises(BlockedAddressError):
        ensure_public_url(url)


def test_public_literal_and_names_pass_the_url_check():
    ensure_public_url(PUBLIC_URL)
    ensure_public_url("https://example.org/page")  # names are checked when resolved


async def test_resolver_refuses_a_name_that_resolves_to_loopback():
    resolver = PublicAddressResolver()
    try:
        with pytest.raises(BlockedAddressError, match="localhost"):
            await resolver.resolve("localhost", 80)
    finally:
        await resolver.close()


class FakeResponse:
    def __init__(self, status, location=None, url=PUBLIC_URL):
        self.status = status
        self.headers = {"Location": location} if location else {}
        self.url = URL(url)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    content_type = "text/html"
    content_length = None
    charset = None

    @property
    def content(self):
        return self

    async def iter_chunked(self, size):
        yield b"page"


class FakeSession:
    """Answers each GET with the next canned response and records the URLs asked for."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.asked = []

    def get(self, url, **kwargs):
        self.asked.append(url)
        assert kwargs["allow_redirects"] is False
        return self.responses.pop(0)


async def test_redirect_to_a_metadata_address_is_refused_before_it_is_fetched():
    session = FakeSession(FakeResponse(302, "http://169.254.169.254/latest/meta-data/"))
    strategy = GetRequestStrategy(check_addresses=True)
    with pytest.raises(BlockedAddressError):
        await strategy.execute(session, {"url": PUBLIC_URL})
    assert session.asked == [PUBLIC_URL]


async def test_relative_redirect_is_followed_and_checked():
    session = FakeSession(FakeResponse(301, "/next"), FakeResponse(200))
    strategy = GetRequestStrategy(check_addresses=True)
    assert await strategy.execute(session, {"url": PUBLIC_URL}) == "page"
    assert session.asked == [PUBLIC_URL, "http://93.184.216.34/next"]


@asynccontextmanager
async def local_server(handler):
    """A real HTTP server on 127.0.0.1; yields (base_url, list of paths requested)."""
    hits: list[str] = []

    async def record(request):
        hits.append(request.path)
        return await handler(request)

    app = web.Application()
    app.router.add_get("/{tail:.*}", record)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    try:
        yield f"http://127.0.0.1:{port}", hits
    finally:
        await runner.cleanup()


async def hello(request):
    return web.Response(text="hello", content_type="text/html")


async def test_default_client_never_reaches_a_local_server():
    async with local_server(hello) as (base, hits):
        client = NetworkClient()
        try:
            with pytest.raises(BlockedAddressError):
                await client.emit_request({"url": base + "/page"})
            with pytest.raises(BlockedAddressError):
                await client.emit_request({"url": base.replace("127.0.0.1", "localhost") + "/p"})
        finally:
            await client.close()
        assert hits == []


async def test_the_flag_allows_a_local_server():
    async with local_server(hello) as (base, hits):
        client = NetworkClient(allow_private_addresses=True)
        try:
            assert await client.emit_request({"url": base + "/page"}) == "hello"
        finally:
            await client.close()
        assert hits == ["/page"]


async def test_endless_redirects_stop_at_the_bound():
    async def loop(request):
        raise web.HTTPFound("/again")

    async with local_server(loop) as (base, hits):
        client = NetworkClient(allow_private_addresses=True)
        try:
            with pytest.raises(TooManyRedirectsError):
                await client.emit_request({"url": base + "/start"})
        finally:
            await client.close()
        assert len(hits) == MAX_REDIRECTS + 1
