from abc import ABC, abstractmethod
from typing import Any

import aiohttp
from yarl import URL

from config import MAX_REDIRECTS, MAX_RESPONSE_BYTES

from .fetch_errors import (
    FetchRejectedError,
    ResponseTooLargeError,
    TooManyRedirectsError,
    UnsupportedContentTypeError,
)
from .url_guard import PublicAddressResolver, ensure_public_url

READ_CHUNK_BYTES = 64 * 1024
DEFAULT_TEXT_ENCODING = "utf-8"
REDIRECT_STATUSES = (301, 302, 303, 307, 308)


class RequestStrategy(ABC):
    """Executes one HTTP method against an aiohttp session.

    `check_addresses` is True when the client refuses non-public addresses
    (see `NetworkClient`); the strategy then checks every URL it is about to
    connect to.
    """

    def __init__(
        self,
        check_addresses: bool = False,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        max_redirects: int = MAX_REDIRECTS,
    ):
        self.check_addresses = check_addresses
        self.max_response_bytes = max_response_bytes
        self.max_redirects = max_redirects

    @abstractmethod
    async def execute(self, session: aiohttp.ClientSession, params: dict) -> Any:
        pass


class GetRequestStrategy(RequestStrategy):
    async def execute(self, session: aiohttp.ClientSession, params: dict) -> Any:
        """GET `params["url"]`, following at most `max_redirects` redirects
        itself so each target is checked before it is connected to.
        """
        url = params["url"]
        for _ in range(self.max_redirects + 1):
            if self.check_addresses:
                ensure_public_url(url)
            async with session.get(
                url=url,
                headers=params.get("headers"),
                allow_redirects=False,
            ) as response:
                location = response.headers.get("Location")
                if response.status not in REDIRECT_STATUSES or not location:
                    response.raise_for_status()
                    return await self._read_text(response, params.get("content_types"))
                url = str(response.url.join(URL(location)))
        raise TooManyRedirectsError(
            f"More than {self.max_redirects} redirects from {params['url']}; "
            "the page was not fetched."
        )

    async def _read_text(
        self, response: aiohttp.ClientResponse, content_types: tuple[str, ...] | None
    ) -> str:
        """The body as text, refused unread when its type is not in
        `content_types` (None accepts any) and abandoned once it passes
        `max_response_bytes`. The count is of decompressed bytes, read chunk
        by chunk, so a small compressed bomb stops at the limit too.
        """
        if content_types is not None and response.content_type not in content_types:
            raise UnsupportedContentTypeError(
                f"{response.url} is {response.content_type!r}, not one of "
                f"{', '.join(content_types)}; it was not read."
            )
        if (response.content_length or 0) > self.max_response_bytes:
            raise ResponseTooLargeError(
                f"{response.url} announces {response.content_length} bytes, over the "
                f"limit of {self.max_response_bytes}; it was not read."
            )
        body = bytearray()
        async for chunk in response.content.iter_chunked(READ_CHUNK_BYTES):
            body += chunk
            if len(body) > self.max_response_bytes:
                raise ResponseTooLargeError(
                    f"{response.url} is over the limit of {self.max_response_bytes} bytes; "
                    "reading stopped."
                )
        try:
            return body.decode(response.charset or DEFAULT_TEXT_ENCODING, errors="replace")
        except LookupError:  # a charset name Python does not know
            return body.decode(DEFAULT_TEXT_ENCODING, errors="replace")


class PostRequestStrategy(RequestStrategy):
    async def execute(self, session: aiohttp.ClientSession, params: dict) -> Any:
        if self.check_addresses:
            ensure_public_url(params["url"])
        async with session.post(
            url=params["url"],
            headers=params.get("headers"),
            json=params.get("data"),
            # A redirect target cannot be checked ahead of the connect.
            allow_redirects=not self.check_addresses,
        ) as response:
            response.raise_for_status()
            return await response.json()


class NetworkClient:
    """Lazily-connected HTTP client shared by every request the crawler makes.

    One aiohttp session is opened on first use and reused for the life of
    the crawl; call `close()` once the crawl finishes.

    Unless `allow_private_addresses` is set, the client only connects to
    public addresses (infrastructure/url_guard.py): a link on a crawled page
    must not reach loopback, the local network or a cloud metadata service.
    Operator-chosen servers, such as a local LLM endpoint, need the flag.

    A GET follows at most `max_redirects` redirects, reads at most `max_response_bytes`
    of body (after decompression), and with `params["content_types"]` only accepts
    those content types.
    """

    def __init__(
        self,
        total_timeout: float = 30,
        connect_timeout: float = 10,
        allow_private_addresses: bool = False,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        max_redirects: int = MAX_REDIRECTS,
    ):
        self.total_timeout = total_timeout
        self.connect_timeout = connect_timeout
        self.allow_private_addresses = allow_private_addresses
        self.session: aiohttp.ClientSession | None = None
        check_addresses = not allow_private_addresses
        self._strategies = {
            "GET": GetRequestStrategy(check_addresses, max_response_bytes, max_redirects),
            "POST": PostRequestStrategy(check_addresses),
        }

    async def emit_request(self, params: dict) -> Any:
        """Dispatch one request per `params["method"]` (default "GET").

        Raises:
            ValueError: If `params["method"]` has no registered strategy.
            BlockedAddressError: If the target, or a redirect target, is not a
                public address and `allow_private_addresses` is off.
        """
        if self.session is None:
            self.session = self._open_session()

        method = params.get("method", "GET").upper()
        strategy = self._strategies.get(method)
        if not strategy:
            raise ValueError(f"Unknown HTTP method: {method!r}")

        try:
            return await strategy.execute(self.session, params)
        except aiohttp.ClientConnectorError as error:
            # The resolver's refusal arrives wrapped as a connect failure.
            if isinstance(error.os_error, FetchRejectedError):
                raise error.os_error from error
            raise

    def _open_session(self) -> aiohttp.ClientSession:
        connector = (
            None
            if self.allow_private_addresses
            else aiohttp.TCPConnector(resolver=PublicAddressResolver())
        )
        return aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.total_timeout, connect=self.connect_timeout),
            connector=connector,
        )

    async def close(self) -> None:
        if self.session:
            await self.session.close()
            self.session = None
