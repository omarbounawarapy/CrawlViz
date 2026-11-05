"""Every key the key store holds is redacted from log lines, whoever uses the store.

The tests use a bare KeyManager, with no crawler and no route around it, so a key reaches
the redaction list only because the key store put it there.
"""

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from config.paths import KEYS_FILE_NAME
from infrastructure.key_manager import KEYS_FILE_MODE, KeyManager
from traceability.logging_setup import JsonLineFormatter
from utils.log_redaction import REDACTED, clear_registered_secrets

API_KEY = "gsk_ThisIsAFakeKeyForTests1234567890"
SECOND_API_KEY = "AIzaSySecondFakeKey0987654321"


@pytest.fixture(autouse=True)
def no_registered_secrets() -> Iterator[None]:
    clear_registered_secrets()
    yield
    clear_registered_secrets()


@pytest.fixture
def keys_path(tmp_path: Path) -> Path:
    return tmp_path / KEYS_FILE_NAME


def write_keys(path: Path, registry: dict[str, list[str]]) -> None:
    path.write_text(json.dumps(registry), encoding="utf-8")
    path.chmod(KEYS_FILE_MODE)


def formatted_log_line(message: str, *args: object) -> str:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, message, args, None)
    return JsonLineFormatter().format(record)


def test_a_key_loaded_by_the_key_store_alone_is_redacted(keys_path: Path) -> None:
    write_keys(keys_path, {"groq": [API_KEY], "gemini": [SECOND_API_KEY]})
    KeyManager(keys_file=keys_path)
    line = formatted_log_line("first %s second %s", API_KEY, SECOND_API_KEY)
    assert API_KEY not in line
    assert SECOND_API_KEY not in line
    assert json.loads(line)["message"] == f"first {REDACTED} second {REDACTED}"


def test_a_key_added_to_the_key_store_is_redacted(keys_path: Path) -> None:
    write_keys(keys_path, {})
    KeyManager(keys_file=keys_path).add_key("groq", f"  {API_KEY}\n")
    assert API_KEY not in formatted_log_line("retry with %s", API_KEY)


def test_a_key_that_arrives_on_reload_is_redacted(keys_path: Path) -> None:
    write_keys(keys_path, {"groq": [API_KEY]})
    manager = KeyManager(keys_file=keys_path)
    write_keys(keys_path, {"groq": [API_KEY], "gemini": [SECOND_API_KEY]})
    manager.reload()
    assert SECOND_API_KEY not in formatted_log_line("calling with %s", SECOND_API_KEY)
