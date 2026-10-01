import aiohttp
from yarl import URL

from pipelines.requests_pipeline import is_rate_limited


def _err(status):
    info = aiohttp.RequestInfo(URL("http://x"), "GET", {}, URL("http://x"))
    return aiohttp.ClientResponseError(info, (), status=status)


def test_429_status_is_rate_limited():
    assert is_rate_limited(_err(429))


def test_other_statuses_are_not():
    assert not is_rate_limited(_err(500))


def test_message_text_alone_is_not():
    assert not is_rate_limited(ValueError("page about HTTP 429 Too Many Requests"))
