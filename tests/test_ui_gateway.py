"""The UI gateway serves snapshot catch-up and broadcasts on the current
websockets asyncio API, on a port the caller can choose."""

import asyncio
import json

import pytest
from websockets.asyncio.client import connect

from ui_bridge import CrawlStateSnapshot, UIWebSocketGateway


@pytest.mark.asyncio
async def test_client_gets_snapshot_then_broadcast_and_stop_closes_server():
    gateway = UIWebSocketGateway(CrawlStateSnapshot(), port=0)
    task = asyncio.create_task(gateway.start())
    for _ in range(100):
        if gateway._server is not None:
            break
        await asyncio.sleep(0.01)

    async with connect(f"ws://localhost:{gateway.port}") as ws:
        first = json.loads(await asyncio.wait_for(ws.recv(), 2))
        assert first["type"] == "SNAPSHOT_FULL"
        await asyncio.sleep(0.05)
        await gateway.broadcast({"type": "PING_TEST"})
        assert json.loads(await asyncio.wait_for(ws.recv(), 2)) == {"type": "PING_TEST"}

    await gateway.stop()
    await asyncio.wait_for(task, 2)
