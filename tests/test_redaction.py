import time

import aiohttp
import pytest
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from config.redaction import (
    REDACTED,
    is_secret_name,
    redact_text,
    safe_error_message,
    sanitize_url,
    url_carries_credentials,
)

FAKE_KEY = "FAKEKEY-0123456789"


def _client_response_error(status: int = 401) -> aiohttp.ClientResponseError:
    url = URL(f"https://user:hunter2@api.example/v1/models?key={FAKE_KEY}")
    headers = CIMultiDictProxy(
        CIMultiDict({"x-goog-api-key": FAKE_KEY, "Authorization": f"Bearer {FAKE_KEY}"})
    )
    info = aiohttp.RequestInfo(url, "POST", headers, url)
    return aiohttp.ClientResponseError(info, (), status=status, message="Unauthorized")


def test_sanitize_url_drops_user_info_query_and_fragment() -> None:
    cleaned = sanitize_url(f"https://user:pw@api.example:8443/v1/m?key={FAKE_KEY}#frag")

    assert cleaned == "https://api.example:8443/v1/m"


def test_sanitize_url_keeps_a_plain_url() -> None:
    assert sanitize_url("http://localhost:11434/api/chat") == "http://localhost:11434/api/chat"


def test_safe_error_message_is_class_and_status_without_the_text() -> None:
    message = safe_error_message(_client_response_error(429))

    assert message == "ClientResponseError (HTTP 429)"
    assert FAKE_KEY not in message


def test_safe_error_message_for_an_error_without_status() -> None:
    assert safe_error_message(ValueError(f"bad key {FAKE_KEY}")) == "ValueError"


def test_redact_text_masks_the_repr_of_a_client_response_error() -> None:
    cleaned = redact_text(repr(_client_response_error()))

    assert FAKE_KEY not in cleaned
    assert "hunter2" not in cleaned
    assert "status=401" in cleaned


def test_redact_text_masks_the_str_of_a_client_response_error() -> None:
    cleaned = redact_text(str(_client_response_error()))

    assert FAKE_KEY not in cleaned
    assert "401" in cleaned


@pytest.mark.parametrize(
    "line",
    [
        f"Authorization: Bearer {FAKE_KEY}",
        f"authorization: Basic {FAKE_KEY}",
        f"x-api-key: {FAKE_KEY}",
        f"X-Goog-Api-Key: {FAKE_KEY}",
        f"{{'x-goog-api-key': '{FAKE_KEY}'}}",
        f'{{"Authorization": "Bearer {FAKE_KEY}"}}',
        f"GET https://api.example/v1?alt=sse&key={FAKE_KEY}&x=1",
        f"GET https://api.example/v1?api_key={FAKE_KEY}",
        f"GET https://api.example/v1?access_token={FAKE_KEY}",
        f"https://user:{FAKE_KEY}@api.example/v1",
        f"password={FAKE_KEY}",
        f"Cookie: session={FAKE_KEY}",
    ],
)
def test_redact_text_masks_header_and_query_shapes(line: str) -> None:
    cleaned = redact_text(line)

    assert FAKE_KEY not in cleaned
    assert REDACTED in cleaned


def test_redact_text_keeps_ordinary_lines() -> None:
    line = "page 12/40 scored, max_tokens=512, tokens: 900, GET https://site.example/a?page=2"

    assert redact_text(line) == line


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Authorization", True),
        ("x-api-key", True),
        ("X-Goog-Api-Key", True),
        ("Proxy-Authorization", True),
        ("X-Auth-Token", True),
        ("Cookie", True),
        ("Accept", False),
        ("User-Agent", False),
        ("max_tokens", False),
    ],
)
def test_is_secret_name(name: str, expected: bool) -> None:
    assert is_secret_name(name) is expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://api.example/v1", False),
        ("http://localhost:11434/v1?model=llama", False),
        ("https://user:pw@api.example/v1", True),
        ("https://user@api.example/v1", True),
        (f"https://api.example/v1?key={FAKE_KEY}", True),
        (f"https://api.example/v1?alt=sse&api_key={FAKE_KEY}", True),
        (f"https://api.example/v1?access_token={FAKE_KEY}", True),
    ],
)
def test_url_carries_credentials(url: str, expected: bool) -> None:
    assert url_carries_credentials(url) is expected


LONG_WORD_CHARS = 100_000
LINEAR_TIME_LIMIT_SECONDS = 0.5


def _seconds(call: object) -> float:
    started = time.perf_counter()
    call()  # type: ignore[operator]
    return time.perf_counter() - started


@pytest.mark.parametrize("filler", ["a", "api_key", "-", "http://", "key", "token:"])
def test_redact_text_takes_linear_time_on_a_long_word(filler: str) -> None:
    word = (filler * LONG_WORD_CHARS)[:LONG_WORD_CHARS]

    assert _seconds(lambda: redact_text(word)) < LINEAR_TIME_LIMIT_SECONDS
    assert _seconds(lambda: redact_text("http://" + word)) < LINEAR_TIME_LIMIT_SECONDS


def test_is_secret_name_takes_linear_time_on_a_long_name() -> None:
    word = "a" * LONG_WORD_CHARS

    assert _seconds(lambda: is_secret_name(word)) < LINEAR_TIME_LIMIT_SECONDS


def test_url_carries_credentials_takes_linear_time_on_a_long_query_name() -> None:
    url = "https://api.example/v1?" + "a" * LONG_WORD_CHARS + "=1"

    assert _seconds(lambda: url_carries_credentials(url)) < LINEAR_TIME_LIMIT_SECONDS
