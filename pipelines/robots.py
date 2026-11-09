import asyncio
import logging
import re
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import aiohttp

from .contracts import Fetcher

logger = logging.getLogger(__name__)

# RFC 9309: a robots.txt that answers 4xx does not exist, so everything is allowed;
# one that answers 5xx or cannot be reached means the site is off limits for now.
HTTP_CLIENT_ERROR_MIN = 400
HTTP_SERVER_ERROR_MIN = 500
# A failed read is not remembered for the whole crawl: the origin is asked again after
# this long, so one outage does not close a site until the crawl ends.
FAILED_READ_RETRY_SECONDS = 60.0
# A robots.txt asking for a longer Crawl-delay is obeyed up to this pace, so a hostile
# or mistaken file cannot stall the crawl.
MAX_CRAWL_DELAY_SECONDS = 60.0
FALLBACK_PRODUCT_TOKEN = "CrawlViz"

_PRODUCT_TOKEN = re.compile(r"[A-Za-z0-9_-]+")


def product_token(user_agent: str) -> str:
    """The name robots.txt groups address: the User-Agent's leading product,
    so ``CrawlViz/1.0 (+contact)`` is matched as ``CrawlViz``."""
    match = _PRODUCT_TOKEN.match(user_agent.strip())
    return match.group(0) if match else FALLBACK_PRODUCT_TOKEN


class RobotsPolicy:
    """robots.txt check, fetched once per origin through the crawl's own fetcher.

    A 4xx means the site has no robots.txt and everything is allowed. A 5xx or a
    fetch that fails (network error, timeout) fails closed: nothing on that origin
    is fetched until a later read succeeds. Concurrent workers asking about the
    same origin share one fetch.
    """

    def __init__(
        self,
        fetcher: Fetcher,
        user_agent: str,
        headers: dict | None = None,
        ttl: float = 0.0,
    ):
        self.fetcher = fetcher
        self.user_agent = user_agent
        self.token = product_token(user_agent)
        self.headers = headers or {}
        # ttl 0 keeps a parsed robots.txt for the whole crawl.
        self.ttl = ttl
        self._parsers: dict[str, RobotFileParser] = {}
        self._expires_at: dict[str, float | None] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def allowed(self, url: str) -> bool:
        parser = await self._parser_for(url)
        return parser.can_fetch(self.token, url)

    async def crawl_delay(self, url: str) -> float | None:
        """Seconds the site asks between requests, capped; None when it names none."""
        delay = (await self._parser_for(url)).crawl_delay(self.token)
        if delay is None:
            return None
        return min(float(delay), MAX_CRAWL_DELAY_SECONDS)

    async def _parser_for(self, url: str) -> RobotFileParser:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        parser = self._fresh(origin)
        if parser is not None:
            return parser
        # One lock per origin: workers that arrive while the file is being read
        # wait for it and then find the parser cached.
        async with self._locks.setdefault(origin, asyncio.Lock()):
            parser = self._fresh(origin)
            if parser is None:
                parser, retry_after = await self._load(origin)
                self._parsers[origin] = parser
                self._expires_at[origin] = self._expiry(retry_after)
            return parser

    def _fresh(self, origin: str) -> RobotFileParser | None:
        parser = self._parsers.get(origin)
        expires_at = self._expires_at.get(origin)
        if parser is None or (expires_at is not None and time.monotonic() >= expires_at):
            return None
        return parser

    def _expiry(self, retry_after: float | None) -> float | None:
        if retry_after is not None:
            return time.monotonic() + retry_after
        return time.monotonic() + self.ttl if self.ttl > 0 else None

    async def _load(self, origin: str) -> tuple[RobotFileParser, float | None]:
        """The origin's parser, and how long until a failed read is retried (None: keep it)."""
        parser = RobotFileParser()
        try:
            text = await self.fetcher.emit_request(
                {
                    "url": f"{origin}/robots.txt",
                    "headers": self.headers,
                    "data": "",
                    "method": "GET",
                }
            )
        except aiohttp.ClientResponseError as error:
            if HTTP_CLIENT_ERROR_MIN <= error.status < HTTP_SERVER_ERROR_MIN:
                parser.allow_all = True
                return parser, None
            logger.warning(
                "robots.txt of %s answered %s; disallowing the origin", origin, error.status
            )
        except Exception:
            logger.warning(
                "robots.txt of %s could not be read; disallowing the origin", origin, exc_info=True
            )
        else:
            parser.parse((text or "").splitlines())
            return parser, None
        parser.disallow_all = True
        return parser, FAILED_READ_RETRY_SECONDS
