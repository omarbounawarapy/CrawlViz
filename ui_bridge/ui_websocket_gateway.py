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
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Set

try:
    from websockets.asyncio.server import Server, ServerConnection, serve
    from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
except ImportError:
    raise ImportError("The 'websockets' package is required. Install with: pip install websockets")

from config import CORS_ORIGIN_REGEX, CORS_ORIGINS

from .crawl_state_snapshot import CrawlStateSnapshot

log = logging.getLogger("ui_bridge.gateway")


@dataclass(frozen=True)
class KeepAlive:
    """Seconds between keep-alive pings, and to wait for an answer, so a vanished tab is noticed."""

    interval: float
    timeout: float


# An entry the websockets library accepts: an exact origin, a pattern, or None for a client
# that sends no Origin header (a script, not a browser page).
OriginRule = str | re.Pattern[str] | None


def default_allowed_origins() -> list[OriginRule]:
    """The origins the API allows for CORS, plus clients that send no Origin.

    A browser page always sends its Origin on a WebSocket handshake, and a WebSocket is not
    bound by CORS, so without this check any web page could read the live crawl."""
    rules: list[OriginRule] = [*CORS_ORIGINS, None]
    if CORS_ORIGIN_REGEX:
        rules.append(re.compile(CORS_ORIGIN_REGEX))
    return rules


class UIWebSocketGateway:
    """
    Pure transport layer.  Knows nothing about crawl events or domain state
    beyond reading an opaque snapshot dict for new-client catch-up.
    """

    def __init__(
        self,
        snapshot: CrawlStateSnapshot,
        keep_alive: KeepAlive,
        host: str = "localhost",
        port: int = 8765,
        allowed_origins: Sequence[OriginRule] | None = None,
    ) -> None:
        self._snapshot: CrawlStateSnapshot = snapshot
        self._keep_alive: KeepAlive = keep_alive
        self._host: str = host
        self._port: int = port
        self._allowed_origins: Sequence[OriginRule] = (
            allowed_origins if allowed_origins is not None else default_allowed_origins()
        )
        self._clients: Set[ServerConnection] = set()
        self._server: Server | None = None

    @property
    def port(self) -> int:
        """The bound port (differs from the requested one when it was 0)."""
        if self._server is not None and self._server.sockets:
            return self._server.sockets[0].getsockname()[1]
        return self._port

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Run the server until the crawl ends (cancelled externally)."""
        self._server = await serve(
            self._on_client_connected,
            self._host,
            self._port,
            origins=self._allowed_origins,
            ping_interval=self._keep_alive.interval,
            ping_timeout=self._keep_alive.timeout,
        )
        log.info("UIWebSocketGateway listening on ws://%s:%d", self._host, self._port)
        try:
            await self._server.wait_closed()
        finally:
            # A cancelled start() must not leave the port bound for the next crawl.
            await self.stop()

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    # ------------------------------------------------------------------
    # Connection handler
    # ------------------------------------------------------------------

    async def _on_client_connected(self, ws: ServerConnection) -> None:
        self._clients.add(ws)
        log.info("Client connected  — active=%d", len(self._clients))

        try:
            # Catch-up: send full current state so a late-joining UI is
            # immediately consistent with the running crawl.
            await ws.send(json.dumps(self._snapshot.to_full_snapshot(), default=str))

            # Push-only stream: discard any client messages (none expected).
            async for _ in ws:
                pass

        except ConnectionClosedOK:
            pass
        except ConnectionClosedError as exc:
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

        payload = json.dumps(message, default=str)
        dead: Set[ServerConnection] = set()

        for ws in set(self._clients):  # snapshot set; safe against mutation
            try:
                await ws.send(payload)
            except Exception:
                dead.add(ws)

        self._clients -= dead
