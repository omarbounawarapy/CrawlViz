from urllib.parse import urljoin,urlparse


from lxml import html


def apply_selector(context, selector):
    if isinstance(context, str):
        context = html.fromstring(context)

    result = context.xpath(selector)

    # -----------------------------
    # NORMALIZE OUTPUT SAFELY
    # -----------------------------
    if result is None:
        return []

    if isinstance(result, (str, bool, int, float)):
        return [result]

    return list(result)

def build_url(base, path):
    return urljoin(base, path)


def is_absolute_url(url):
    parsed = urlparse(url)
    return bool(parsed.scheme and parsed.netloc)

def is_relative_url(url):
    return not is_absolute_url(url)
