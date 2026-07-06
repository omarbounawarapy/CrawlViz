from typing import Any
from urllib.parse import urljoin, urlparse

from lxml import html


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


def is_absolute_url(url: str) -> bool:
    parsed = urlparse(url)
    return bool(parsed.scheme and parsed.netloc)


def is_relative_url(url: str) -> bool:
    return not is_absolute_url(url)
