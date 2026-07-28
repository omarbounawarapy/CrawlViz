"""
UIWebSocketGateway
==================
Network boundary of the UI integration layer.

Responsibilities (exactly these, nothing more):
  - Accept and track WebSocket connections from React frontend clients.
  - Send SNAPSHOT_FULL to every new client on connect (catch-up).
  - Broadcast pre-serialised UI messages to all active clients.
  - Evict dead connections without crashing the crawl.

Design invariants:
  - No domain event handling.
  - No snapshot mutation.
  - No business logic of any kind.
  - The snapshot reference is read-only (only to_full_snapshot() is called).
"""

from __future__ import annotations

import json
import logging
from typing import Set

try:
    import websockets
    import websockets.exceptions
    from websockets.server import WebSocketServerProtocol
except ImportError:
    raise ImportError(
        "The 'websockets' package is required. Install with: pip install websockets"
    )

from .crawl_state_snapshot import CrawlStateSnapshot

log = logging.getLogger("ui_bridge.gateway")


class UIWebSocketGateway:
    """
    Pure transport layer.  Knows nothing about crawl events or domain state
    beyond reading an opaque snapshot dict for new-client catch-up.
    """

    def __init__(
        self,
        snapshot: CrawlStateSnapshot,
        host: str = "localhost",
        port: int = 8765,
    ) -> None:
        self._snapshot: CrawlStateSnapshot = snapshot
        self._host:     str                = host
        self._port:     int                = port
        self._clients:  Set[WebSocketServerProtocol] = set()
        self._server                       = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Run the server until the crawl ends (cancelled externally)."""
        self._server = await websockets.serve(
            self._on_client_connected,
            self._host,
            self._port,
            ping_interval=20,
            ping_timeout=10,
        )
        log.info("UIWebSocketGateway listening on ws://%s:%d", self._host, self._port)
        await self._server.wait_closed()

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    # ------------------------------------------------------------------
    # Connection handler
    # ------------------------------------------------------------------

    async def _on_client_connected(self, ws: WebSocketServerProtocol) -> None:
        self._clients.add(ws)
        log.info("Client connected  — active=%d", len(self._clients))

        try:
            # Catch-up: send full current state so a late-joining UI is
            # immediately consistent with the running crawl.
            await ws.send(json.dumps(self._snapshot.to_full_snapshot(), default=str))

            # Push-only stream: discard any client messages (none expected).
            async for _ in ws:
                pass

        except websockets.exceptions.ConnectionClosedOK:
            pass
        except websockets.exceptions.ConnectionClosedError as exc:
            log.debug("Client closed with error: %s", exc)
        finally:
            self._clients.discard(ws)
            log.info("Client disconnected — active=%d", len(self._clients))

    # ------------------------------------------------------------------
    # Broadcast  (called by TelemetryBridge only)
    # ------------------------------------------------------------------

    async def broadcast(self, message: dict) -> None:
        """
        Serialise message once, fan out to all connected clients.

        Dead connections are detected during send and silently pruned.
        Message must already be a plain JSON-serialisable dict.
        """
        if not self._clients:
            return

        payload  = json.dumps(message, default=str)
        dead: Set[WebSocketServerProtocol] = set()

        for ws in set(self._clients):          # snapshot set; safe against mutation
            try:
                await ws.send(payload)
            except Exception:
                dead.add(ws)

        self._clients -= dead
