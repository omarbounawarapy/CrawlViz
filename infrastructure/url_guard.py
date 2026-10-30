"""Address policy for page fetches: only public hosts are reachable.

A crawl follows links from untrusted pages, so a page can point at
``http://169.254.169.254/`` (cloud metadata), ``http://localhost:8000/`` (this
app's own API) or an internal host. `ensure_public_url` rejects such targets by
address, and `PublicAddressResolver` rejects them again at connect time, on the
addresses the connection will really use, so a hostname that resolves to a
private address (or changes its answer between the check and the connect) is
also refused.
"""

import ipaddress
import socket
from urllib.parse import urlsplit

from aiohttp.abc import AbstractResolver, ResolveResult
from aiohttp.resolver import ThreadedResolver

from .fetch_errors import BlockedAddressError

ALLOWED_SCHEMES = ("http", "https")


def is_blocked_address(address: str) -> bool:
    """True when `address` is not a public unicast IP address.

    Covers loopback, RFC 1918 private ranges, link-local (including the cloud
    metadata address 169.254.169.254), carrier-grade NAT (100.64.0.0/10, which
    holds Alibaba's metadata address), unique-local IPv6, multicast,
    unspecified and reserved ranges. An IPv4 address wrapped in IPv6
    (``::ffff:127.0.0.1``) is judged as the IPv4 address it carries.
    """
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_multicast or not ip.is_global


def ensure_public_url(url: str) -> None:
    """Raise `BlockedAddressError` unless `url` is http(s) and its host, when
    it is an IP literal, is public. Host names are checked at connect time by
    `PublicAddressResolver`, because only the connection knows which address
    it will use.
    """
    parts = urlsplit(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise BlockedAddressError(f"Only http and https can be fetched, not {parts.scheme!r}.")
    host = parts.hostname
    if not host:
        raise BlockedAddressError(f"The URL {url!r} has no host.")
    try:
        ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return  # a name: resolved and checked by PublicAddressResolver
    if is_blocked_address(host):
        raise BlockedAddressError(f"{host} is not a public address, so it is not fetched.")


class PublicAddressResolver(AbstractResolver):
    """Resolves names like the default resolver, then refuses private answers.

    Install it on the connector so the check covers the address the socket
    connects to, for the first request and for every redirect.
    """

    def __init__(self) -> None:
        self._inner = ThreadedResolver()

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        results = await self._inner.resolve(host, port, family)
        blocked = [entry["host"] for entry in results if is_blocked_address(entry["host"])]
        if blocked:
            raise BlockedAddressError(
                f"{host} resolves to {blocked[0]}, which is not a public address."
            )
        return results

    async def close(self) -> None:
        await self._inner.close()
