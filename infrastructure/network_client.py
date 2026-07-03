import aiohttp
from abc import ABC, abstractmethod
from typing import Any


class RequestStrategy(ABC):
    @abstractmethod
    async def execute(self, session: aiohttp.ClientSession, params: dict) -> Any:
        pass


class GetRequestStrategy(RequestStrategy):
    async def execute(self, session: aiohttp.ClientSession, params: dict) -> Any:
        async with session.get(
            url=params["url"],
            headers=params.get("headers"),
        ) as response:
            response.raise_for_status()
            return await response.text()


class PostRequestStrategy(RequestStrategy):
    async def execute(self, session: aiohttp.ClientSession, params: dict) -> Any:
        async with session.post(
            url=params["url"],
            headers=params.get("headers"),
            json=params.get("data"),
        ) as response:
            response.raise_for_status()
            return await response.json()


class NetworkClient:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
        self._strategies = {
            "GET": GetRequestStrategy(),
            "POST": PostRequestStrategy(),
        }

    async def emit_request(self, params: dict) -> Any:
        if self.session is None:
            self.session = aiohttp.ClientSession()

        method = params.get("method", "GET").upper()
        strategy = self._strategies.get(method)
        if not strategy:
            raise ValueError(f"Unsupported HTTP method: {method}")

        return await strategy.execute(self.session, params)

    async def close(self) -> None:
        if self.session:
            await self.session.close()
            self.session = None