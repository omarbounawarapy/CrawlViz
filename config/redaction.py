"""The one place that masks secrets in text, URLs and error messages.

Trace events, scoring failures and benchmark job logs reach disk and the UI, so no
credential may be in them. Three helpers cover the ways a secret travels:

- ``sanitize_url`` for a URL that is recorded as a field,
- ``safe_error_message`` for an exception that is recorded in place of ``str(exc)``,
- ``redact_text`` for free text that might hold a header, a key or a request dump.

``str(aiohttp.ClientResponseError)`` carries the request URL, and its ``repr`` carries
the request headers, so an exception is described by its class and HTTP status only.

This module lives in ``config`` because every other backend package already imports
``config``, so any of them can use it without an import cycle.
"""

import re
from urllib.parse import parse_qsl, urlsplit, urlunsplit

REDACTED = "[redacted]"

# Header and key names that hold a credential. ``token`` and ``auth`` must end the name
# so that counts such as ``max_tokens`` are kept.
_SECRET_NAME = (
    r"[\w-]*(?:authorization|api[-_]?key|secret|passw(?:or)?d|cookie|token\b|auth\b)[\w-]*"
)
_SECRET_NAME_PATTERN = re.compile(_SECRET_NAME, re.IGNORECASE)

# ``name: value``, ``name=value``, ``'name': 'value'`` and ``"name": "value"``.
_NAMED_VALUE = re.compile(
    rf"(?P<name>{_SECRET_NAME})(?P<separator>[\"']?\s*[:=]\s*)"
    r"(?:(?P<quote>[\"']).*?(?P=quote)|(?:Bearer|Basic|Token)\s+[^\s\"',&)>}]+|[^\s\"',&)>}]+)",
    re.IGNORECASE,
)
_BEARER = re.compile(r"\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{4,}", re.IGNORECASE)
# Two levels of nested brackets cover ``URL('...')`` and ``<CIMultiDictProxy(...)>``.
_REQUEST_INFO = re.compile(r"RequestInfo\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)")
_QUERY_SECRET = re.compile(
    r"(?P<lead>[?&])(?P<name>key|[\w-]*(?:api[-_]?key|secret|passw(?:or)?d|token|auth)[\w-]*)="
    r"[^&\s\"'<>)]*",
    re.IGNORECASE,
)
_URL_USERINFO = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)[^/\s@\"']+@")


def is_secret_name(name: str) -> bool:
    """True when a header or field called `name` is likely to hold a credential."""
    return _SECRET_NAME_PATTERN.search(name) is not None


def url_carries_credentials(url: str) -> bool:
    """True when `url` has user info or a query value named like a credential."""
    try:
        parts = urlsplit(url)
        has_user_info = bool(parts.username or parts.password)
    except ValueError:
        return False
    query_names = (name for name, _ in parse_qsl(parts.query, keep_blank_values=True))
    return has_user_info or any(
        name.lower() == "key" or is_secret_name(name) for name in query_names
    )


def sanitize_url(url: str) -> str:
    """`url` without user info, query string or fragment; scheme, host, port and path stay."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        netloc = f"{host}:{parts.port}" if parts.port else host
    except ValueError:
        return REDACTED
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def safe_error_message(exc: BaseException) -> str:
    """The exception class, plus the HTTP status when it has one. Never ``str(exc)``."""
    status = getattr(exc, "status", None)
    name = type(exc).__name__
    if isinstance(status, int):
        return f"{name} (HTTP {status})"
    return name


def redact_text(text: str) -> str:
    """`text` with credentials masked.

    Masks request dumps (``RequestInfo(...)``), ``Bearer`` and ``Basic`` tokens, the
    value after a header or key name that looks like a credential (``Authorization``,
    ``x-api-key``, ``x-goog-api-key``, ``password``), user info in URLs, and query values
    named ``key`` or like a credential.
    """
    text = _REQUEST_INFO.sub(f"RequestInfo({REDACTED})", text)
    text = _URL_USERINFO.sub(rf"\g<scheme>{REDACTED}@", text)
    text = _QUERY_SECRET.sub(rf"\g<lead>\g<name>={REDACTED}", text)
    text = _BEARER.sub(rf"\1 {REDACTED}", text)
    return _NAMED_VALUE.sub(rf"\g<name>\g<separator>{REDACTED}", text)
