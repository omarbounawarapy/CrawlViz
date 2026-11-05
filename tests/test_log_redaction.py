"""Secrets never reach a log line (SEC-3)."""

from collections.abc import Iterator

import pytest

from crawlviz.shared import (
    MIN_SECRET_LENGTH,
    REDACTED,
    clear_registered_secrets,
    redact_secrets,
    register_secrets,
)

API_KEY = "gsk_ThisIsAFakeKeyForTests1234567890"


@pytest.fixture(autouse=True)
def no_registered_secrets() -> Iterator[None]:
    clear_registered_secrets()
    yield
    clear_registered_secrets()


def test_a_registered_value_is_replaced_wherever_it_appears() -> None:
    register_secrets([API_KEY])
    line = f"calling provider with {API_KEY} and again {API_KEY}!"
    assert redact_secrets(line) == f"calling provider with {REDACTED} and again {REDACTED}!"


def test_a_value_that_contains_another_is_replaced_whole() -> None:
    register_secrets(["abcdefgh", "abcdefghijkl"])
    assert redact_secrets("key abcdefghijkl end") == f"key {REDACTED} end"


def test_values_shorter_than_the_minimum_are_not_registered() -> None:
    register_secrets(["x" * (MIN_SECRET_LENGTH - 1)])
    assert redact_secrets("xxxxxxx stays") == "xxxxxxx stays"


@pytest.mark.parametrize(
    ("line", "kept", "leaked"),
    [
        ("Authorization: Bearer abc.def-ghi", "Authorization: Bearer ", "abc.def-ghi"),
        ("GET https://api.example/v1?key=AIzaSyFake12345&alt=json", "?key=", "AIzaSyFake12345"),
        ("api_key=supersecretvalue1", "api_key=", "supersecretvalue1"),
        ('{"password": "hunter2hunter2"}', '"password": "', "hunter2hunter2"),
        ("X-Api-Key: 0123456789abcdef", "X-Api-Key: ", "0123456789abcdef"),
    ],
)
def test_credential_shaped_text_is_replaced_without_registration(
    line: str, kept: str, leaked: str
) -> None:
    cleaned = redact_secrets(line)
    assert kept in cleaned
    assert REDACTED in cleaned
    assert leaked not in cleaned


def test_ordinary_text_is_left_alone() -> None:
    line = "max_tokens=1024 used 12 of 40 calls for node n-7 (key count 3)"
    assert redact_secrets(line) == line
