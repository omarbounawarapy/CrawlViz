"""Checks every HTTP request passes before a route sees it.

Three checks, each closing one way a web page could drive the local API:

* Host: the Host header must name this machine or a configured host. A page on
  ``evil.example`` that rebinds its name to 127.0.0.1 sends ``Host: evil.example``, so it is
  refused here even though the browser treats the API as its own origin (DNS rebinding).
* Origin: a request that carries an Origin header must come from an allowed UI origin. A
  browser always sends Origin on a cross-site request, so a hidden form on another site is
  refused. A request with no Origin comes from a script or tool, not a page.
* Content type: POST, PUT, PATCH and DELETE must declare ``application/json``, with or
  without a body. A form or a no-cors fetch cannot send that type without a CORS preflight
  that the allowlist then refuses, which closes the bodyless-POST forgery on ``/stop``,
  ``/config/reset`` and the preset and benchmark-job routes.

WebSocket handshakes are not HTTP requests here; the crawl WebSocket checks its own origins.
"""

import logging
import re
from collections.abc import Collection

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
JSON_MEDIA_TYPE = "application/json"

STATUS_MISDIRECTED_REQUEST = 421
STATUS_FORBIDDEN = 403
STATUS_UNSUPPORTED_MEDIA_TYPE = 415


class RequestRefusalError(Exception):
    """A request failed a guard; carries the reply to send."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def host_name(host_header: str) -> str:
    """The host in a Host header, lower case, without the port. IPv6 keeps its brackets."""
    host = host_header.strip().lower()
    if host.startswith("["):
        closing = host.find("]")
        return host[: closing + 1] if closing != -1 else host
    return host.partition(":")[0]


class RequestGuards:
    """The Host, Origin and content type rules, as plain checks that raise `RequestRefusalError`."""

    def __init__(
        self,
        allowed_hosts: Collection[str],
        allowed_origins: Collection[str],
        allowed_origin_pattern: str | None = None,
    ) -> None:
        self._allowed_hosts = frozenset(name.strip().lower() for name in allowed_hosts)
        self._allowed_origins = frozenset(origin.strip().rstrip("/") for origin in allowed_origins)
        self._origin_pattern = (
            re.compile(allowed_origin_pattern) if allowed_origin_pattern else None
        )

    def check(self, method: str, headers: Headers) -> None:
        """Raise `RequestRefusalError` unless the request passes all three checks."""
        self._check_host(headers.get("host", ""))
        self._check_origin(headers.get("origin"))
        if method.upper() in STATE_CHANGING_METHODS:
            self._check_json_content_type(headers.get("content-type", ""))

    def _check_host(self, host_header: str) -> None:
        if host_name(host_header) not in self._allowed_hosts:
            raise RequestRefusalError(
                STATUS_MISDIRECTED_REQUEST,
                "This API answers only to localhost. Open the app from http://localhost.",
            )

    def _check_origin(self, origin: str | None) -> None:
        if origin is None or self._is_allowed_origin(origin):
            return
        raise RequestRefusalError(
            STATUS_FORBIDDEN,
            "This request came from a page the API does not trust. Use the CrawlViz app.",
        )

    def _is_allowed_origin(self, origin: str) -> bool:
        if origin in self._allowed_origins:
            return True
        pattern = self._origin_pattern
        return pattern is not None and pattern.fullmatch(origin) is not None

    @staticmethod
    def _check_json_content_type(content_type: str) -> None:
        media_type = content_type.partition(";")[0].strip().lower()
        if media_type != JSON_MEDIA_TYPE:
            raise RequestRefusalError(
                STATUS_UNSUPPORTED_MEDIA_TYPE,
                "Requests that change state must send Content-Type: application/json.",
            )


class RequestGuardMiddleware:
    """ASGI middleware that applies `RequestGuards` to every HTTP request."""

    def __init__(
        self,
        app: ASGIApp,
        allowed_hosts: Collection[str],
        allowed_origins: Collection[str],
        allowed_origin_pattern: str | None = None,
    ) -> None:
        self._app = app
        self._guards = RequestGuards(allowed_hosts, allowed_origins, allowed_origin_pattern)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # A CORS preflight is answered by the CORS middleware outside this one and never
        # reaches a route; it has no content type or credentials to check.
        if scope["type"] != "http" or scope["method"] == "OPTIONS":
            await self._app(scope, receive, send)
            return
        try:
            self._guards.check(scope["method"], Headers(scope=scope))
        except RequestRefusalError as refusal:
            logger.warning("Refused %s %r: %s", scope["method"], scope["path"], refusal.detail)
            response = JSONResponse({"detail": refusal.detail}, status_code=refusal.status_code)
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)
