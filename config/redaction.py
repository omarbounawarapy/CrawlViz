"""The one place that masks secrets in text, URLs and error messages.

Trace events, scoring failures and benchmark job logs reach disk and the UI, so no
credential may be in them. Four helpers cover the ways a secret travels:

- ``sanitize_url`` for a URL that is recorded as a field,
- ``safe_error_message`` for an exception that is recorded in place of ``str(exc)``,
- ``redact_text`` for free text that might hold a header, a key or a request dump,
- ``redact_bounded_text`` for free text that is also logged: cut to a limit, then masked.

``str(aiohttp.ClientResponseError)`` carries the request URL, and its ``repr`` carries
the request headers, so an exception is described by its class and HTTP status only.

This module lives in ``config`` because every other backend package already imports
``config``, so any of them can use it without an import cycle.
"""

import re
from urllib.parse import parse_qsl, urlsplit, urlunsplit

REDACTED = "[redacted]"
# The longest text kept in a log line, job log or warning; a longer one is cut and marked.
MAX_BOUNDED_TEXT_CHARS = 4096
TEXT_CUT_MARK = " ...[cut]"

# Header, field and query names that hold a credential: the one rule every helper uses.
# A name is secret when it holds one of these words: ``authorization``, ``api_key``,
# ``secret``, ``password``, ``cookie``, ``token`` (but not the count ``tokens``, a
# ``tokenizer`` or a ``token_usage``), ``auth`` at the start of a word (``auth_code``,
# ``authkey``) or after a lowercase letter that ends a word (``basicAuth``, ``proxyauth``),
# ``oauth_`` (``oauth_verifier``) and ``key`` as a whole word. ``author``, ``authority``,
# ``oauth`` alone, ``monkey`` and ``keys`` are kept. The name is found by its core, and
# the text around the core is bounded, so a long word costs linear time (a ``[\w-]*``
# prefix tried from every position of a long word costs quadratic time).
MAX_NAME_AFFIX_CHARS = 64
_WORD_START = r"(?<![^\W_])"  # the start of the name, or just after ``-`` or ``_``
_TOKEN_THAT_IS_NOT_ONE = r"s(?![a-z0-9])|iz|[-_]?(?:usage|count|limit|budget|total)"
_SECRET_CORE = (
    r"(?:authorization|api[-_]?key|secret|passw(?:or)?d|cookie"
    rf"|token(?!{_TOKEN_THAT_IS_NOT_ONE})"
    rf"|{_WORD_START}auth(?!or)"  # auth_code, authkey, authentication
    r"|(?<=[a-np-z])auth(?![a-z0-9])"  # basicAuth, proxyauth; not oauth, not Unauthorized
    rf"|{_WORD_START}oauth(?=[-_])"  # oauth_verifier; oauth alone is a flag
    rf"|{_WORD_START}key(?![\w-]))"
)
_SECRET_NAME_PATTERN = re.compile(_SECRET_CORE, re.IGNORECASE)
_SECRET_NAME = rf"{_SECRET_CORE}[\w-]{{0,{MAX_NAME_AFFIX_CHARS}}}"

# ``name: value``, ``name=value``, ``'name': 'value'``, ``"name": "value"`` and the pair
# ``(b'name', b'value')`` that a header list prints. A quoted value may carry a ``b``
# prefix and spaces; a quote that never closes (a cut line) masks the rest of the word.
_NAMED_VALUE = re.compile(
    rf"(?P<name>{_SECRET_NAME})"
    r"(?P<separator>[\"']?\s*[:=]\s*|[\"']\s*,\s*)"
    r"(?:b?(?P<quote>[\"']).*?(?P=quote)"
    r"|(?:Bearer|Basic|Token)\s+[^\s\"',&)>}]+"
    r"|b?[\"'][^\s\"',&)>}]*"
    r"|[^\s\"',&)>}]+)",
    re.IGNORECASE,
)
# ``Authorization: ...`` and ``Cookie: ...`` carry several credentials in one value
# (``Digest ... response="..."``, ``a=1; sid=...``), so the whole line is the value.
# A quoted name (``'Cookie': '...'``) is left to ``_NAMED_VALUE``.
_HEADER_LINE = re.compile(
    rf"(?P<name>(?:authorization|cookie)[\w-]{{0,{MAX_NAME_AFFIX_CHARS}}})"
    r"(?P<separator>[ \t]*:[ \t]*)[^\r\n]+",
    re.IGNORECASE,
)
# A scheme word alone is prose ("Basic tests passed"), so a bare value is masked only when
# it is long and token-shaped: letters and digits with a digit or one of ``._~+/=-`` in it.
# After a quote the word is the start of a header value, so its value is masked in any shape.
MIN_BEARER_VALUE_CHARS = 8
_BEARER = re.compile(
    r"\b(Bearer|Basic)\s+"
    rf"(?=[A-Za-z0-9._~+/=-]{{{MIN_BEARER_VALUE_CHARS},}})(?=[A-Za-z]*[\d._~+/=-])"
    r"[A-Za-z0-9._~+/=-]+",
    re.IGNORECASE,
)
_QUOTED_SCHEME_VALUE = re.compile(r"(?<=[\"'])(Bearer|Basic)\s+[^\s\"']+", re.IGNORECASE)
# Two levels of nested brackets cover ``URL('...')`` and ``<CIMultiDictProxy(...)>``.
_REQUEST_INFO = re.compile(r"RequestInfo\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)")
# A URL scheme is short and starts where a word starts.
MAX_SCHEME_CHARS = 32
_URL_USERINFO = re.compile(
    rf"(?P<scheme>(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]{{0,{MAX_SCHEME_CHARS - 1}}}://)"
    r"[^/\s@\"']+@"
)


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
    return has_user_info or any(is_secret_name(name) for name in query_names)


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
    value after a header, field or query name that looks like a credential
    (``Authorization``, ``x-api-key``, ``access_key``, ``password``) and user info in URLs.
    A ``Cookie`` or ``Authorization`` header is masked to the end of its line.
    """
    text = _REQUEST_INFO.sub(f"RequestInfo({REDACTED})", text)
    text = _URL_USERINFO.sub(rf"\g<scheme>{REDACTED}@", text)
    text = _HEADER_LINE.sub(rf"\g<name>\g<separator>{REDACTED}", text)
    text = _QUOTED_SCHEME_VALUE.sub(rf"\1 {REDACTED}", text)
    text = _BEARER.sub(rf"\1 {REDACTED}", text)
    return _NAMED_VALUE.sub(rf"\g<name>\g<separator>{REDACTED}", text)


def redact_bounded_text(
    text: str, *, max_chars: int = MAX_BOUNDED_TEXT_CHARS, was_cut: bool = False
) -> str:
    """`text` cut to `max_chars`, masked, and marked with ``TEXT_CUT_MARK`` when it was cut.

    The text is cut before it is masked, which bounds the cost of masking, and after it,
    because masking can lengthen it. `was_cut` says the caller already dropped the end.
    A secret split by the cut still has its name before it, so it is masked.
    """
    masked = redact_text(text[:max_chars])
    if was_cut or len(text) > max_chars or len(masked) > max_chars:
        return masked[:max_chars] + TEXT_CUT_MARK
    return masked
