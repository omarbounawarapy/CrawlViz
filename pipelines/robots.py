import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from .contracts import Fetcher


class RobotsPolicy:
    """robots.txt check, fetched once per origin through the crawl's own fetcher.

    A missing or unreadable robots.txt allows everything, the usual
    convention for a 4xx; a fetch failure is treated the same way so one
    flaky request cannot halt a crawl.
    """

    def __init__(
        self, fetcher: Fetcher, user_agent: str, headers: dict | None = None,
        ttl: float = 0.0,
    ):
        self.fetcher = fetcher
        self.user_agent = user_agent
        self.headers = headers or {}
        # ttl 0 keeps a parsed robots.txt for the whole crawl.
        self.ttl = ttl
        self._parsers: dict[str, RobotFileParser] = {}
        self._loaded_at: dict[str, float] = {}

    async def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        parser = self._parsers.get(origin)
        expired = (
            parser is not None and self.ttl > 0
            and time.monotonic() - self._loaded_at[origin] >= self.ttl
        )
        if parser is None or expired:
            parser = await self._load(origin)
            self._parsers[origin] = parser
            self._loaded_at[origin] = time.monotonic()
        return parser.can_fetch(self.user_agent, url)

    async def _load(self, origin: str) -> RobotFileParser:
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
            parser.parse((text or "").splitlines())
        except Exception:
            parser.parse([])
        return parser
