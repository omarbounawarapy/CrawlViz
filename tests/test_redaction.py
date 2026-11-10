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
        ("access_key", True),
        ("subscription-key", True),
        ("Ocp-Apim-Subscription-Key", True),
        ("key", True),
        ("monkey", False),
        ("keys", False),
        ("key_count", False),
        ("author", False),
        ("oauth", False),
        ("cookie_policy", True),
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
        (f"https://api.example/v1?access_key={FAKE_KEY}", True),
        (f"https://api.example/v1?subscription-key={FAKE_KEY}", True),
        ("https://api.example/v1?cookie_policy=1", True),
        ("https://api.example/v1?q=cats", False),
        ("https://api.example/v1?model=llama&alt=sse", False),
        ("https://api.example/v1?api-version=2024-02-01", False),
        ("https://api.example/v1?max_tokens=512", False),
        ("https://api.example/v1?author=smith", False),
        ("https://api.example/v1?oauth=1", False),
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


@pytest.mark.parametrize(
    "line",
    [
        f"GET https://api.example/v1?access_key={FAKE_KEY}",
        f"GET https://api.example/v1?subscription-key={FAKE_KEY}&x=1",
        f"key={FAKE_KEY}",
        f"retrying with access_key={FAKE_KEY} now",
        f"Ocp-Apim-Subscription-Key: {FAKE_KEY}",
    ],
)
def test_redact_text_masks_names_that_end_in_key(line: str) -> None:
    cleaned = redact_text(line)

    assert FAKE_KEY not in cleaned
    assert REDACTED in cleaned


@pytest.mark.parametrize(
    "line",
    [
        "GET https://api.example/v1?max_tokens=512",
        "GET https://api.example/v1?author=smith&oauth=1",
        "GET https://api.example/v1?q=cats&model=llama&alt=sse&api-version=2024-02-01",
        "monkey=banana keys=3 key_count=4",
    ],
)
def test_redact_text_keeps_names_that_only_look_like_secrets(line: str) -> None:
    assert redact_text(line) == line


def test_the_query_rule_and_the_name_rule_agree() -> None:
    names = ["key", "api_key", "access_key", "max_tokens", "author", "oauth", "cookie_policy", "q"]

    for name in names:
        masked = redact_text(f"?{name}=VALUE") != f"?{name}=VALUE"
        assert masked == url_carries_credentials(f"https://h/p?{name}=VALUE"), name


@pytest.mark.parametrize(
    ("line", "leaked"),
    [
        ("Cookie: a=1; sid=SECRETSID; theme=dark", ["SECRETSID", "theme=dark"]),
        ("cookie: first=ONE; second=TWO", ["ONE", "TWO"]),
        ("Set-Cookie: sid=SECRETSID; Path=/; HttpOnly", ["SECRETSID", "HttpOnly"]),
        (
            'Authorization: Digest username="u", realm="r", response="SECRETRESP"',
            ["SECRETRESP", "username"],
        ),
        ("Proxy-Authorization: NTLM SECRETNTLM", ["SECRETNTLM"]),
        ("Authorization: Bearer FAKEKEY-0123456789 extra=SECRETEXTRA", ["SECRETEXTRA"]),
    ],
)
def test_redact_text_masks_a_header_value_to_the_end_of_the_line(
    line: str, leaked: list[str]
) -> None:
    cleaned = redact_text(f"before\n{line}\nafter")

    assert not any(piece in cleaned for piece in leaked)
    assert cleaned.startswith("before\n") and cleaned.endswith("\nafter")


@pytest.mark.parametrize(
    "line",
    [
        "Basic tests passed",
        "Basic requirements were met",
        "Bearer tokens are not logged",
        "the Bearer authentication scheme",
    ],
)
def test_redact_text_keeps_prose_that_starts_with_a_scheme_word(line: str) -> None:
    assert redact_text(line) == line


@pytest.mark.parametrize(
    "line",
    [
        f"retry sent Bearer {FAKE_KEY}",
        "token was Basic dXNlcjpwYXNzd29yZA==",
        "sent Bearer eyJhbGciOi.eyJzdWIi.c2ln",
    ],
)
def test_redact_text_masks_a_token_shaped_value_after_a_scheme_word(line: str) -> None:
    cleaned = redact_text(line)

    assert cleaned.split()[-1] == REDACTED
