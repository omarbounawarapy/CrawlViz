import re
from typing import Any
from urllib.parse import quote, urldefrag, urljoin, urlparse, urlunparse

from lxml import etree, html


def apply_selector(context: Any, selector: str) -> list:
    """Run an XPath `selector` against `context` (HTML string or lxml element).

    Normalizes lxml's xpath() return shape -- a list, a single scalar
    (str/bool/int/float for expressions like ``count(...)``), or None --
    into a plain list every caller can iterate uniformly.
    """
    if isinstance(context, str):
        context = html.fromstring(context)

    result = context.xpath(selector)

    if result is None:
        return []

    if isinstance(result, (str, bool, int, float)):
        return [result]

    return list(result)


def build_url(base: str, path: str) -> str:
    return urljoin(base, path)


_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_PERCENT = re.compile(r"%([0-9A-Fa-f]{2})")


def _normalize_percent(text: str) -> str:
    """Decode escapes of unreserved characters, upper-case the rest, escape raw non-ASCII."""

    def fix(m: re.Match) -> str:
        char = chr(int(m.group(1), 16))
        return char if char in _UNRESERVED else "%" + m.group(1).upper()

    return quote(_PERCENT.sub(fix, text), safe="/:@!$&'()*+,;=~%?-._")


def normalize_url(url: str) -> str:
    """Canonical form of a (possibly relative) URL used as node identity.

    Drops the fragment, strips a trailing slash from the path (the root ``/``
    stays), and normalizes percent-encoding, so ``/wiki/X``, ``/wiki/X/`` and
    ``/wiki/X#Y`` are one page.
    """
    url, _ = urldefrag(url.strip())
    parts = urlparse(url)
    path = _normalize_percent(parts.path)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"
    return urlunparse(parts._replace(path=path, query=_normalize_percent(parts.query)))


def is_absolute_url(url: str) -> bool:
    parsed = urlparse(url)
    return bool(parsed.scheme and parsed.netloc)


def is_relative_url(url: str) -> bool:
    return not is_absolute_url(url)


def document_text(page: str) -> str:
    """Main text of an HTML page: the paragraph text, scripts and styles dropped.

    This is what scoring treats as a page's content (``parent.content`` holds the
    raw HTML on a node). ``NLPService.score_links`` applies it, and both the crawl
    and ``tools/nlp_eval.py`` score through that method, so the parent vector is
    built from the same text in both. Pages without paragraphs fall back to all
    visible text.
    """
    if not page or not page.strip():
        return ""
    try:
        tree = html.fromstring(page)
    except (ValueError, etree.ParserError):
        return ""
    for junk in tree.xpath("//script|//style|//noscript"):
        junk.drop_tree()
    paragraphs = tree.xpath("//p[normalize-space()]")
    parts = [" ".join(p.itertext()) for p in paragraphs] or [" ".join(tree.itertext())]
    return re.sub(r"\s+", " ", " ".join(parts)).strip()
