from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from .contracts import Fetcher


class RobotsPolicy:
    """robots.txt check, fetched once per origin through the crawl's own fetcher.

    A missing or unreadable robots.txt allows everything, the usual
    convention for a 4xx; a fetch failure is treated the same way so one
    flaky request cannot halt a crawl.
    """

    def __init__(self, fetcher: Fetcher, user_agent: str, headers: dict | None = None):
        self.fetcher = fetcher
        self.user_agent = user_agent
        self.headers = headers or {}
        self._parsers: dict[str, RobotFileParser] = {}

    async def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        parser = self._parsers.get(origin)
        if parser is None:
            parser = await self._load(origin)
            self._parsers[origin] = parser
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
