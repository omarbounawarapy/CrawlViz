"""The key store writes keys.json so no other file is ever left holding the keys."""

import json
import os
from pathlib import Path

import pytest

from config.paths import KEYS_FILE_NAME
from crawlviz.llm.key_manager import KEYS_FILE_MODE, KeyManager

API_KEY = "gsk_ThisIsAFakeKeyForTests1234567890"


@pytest.fixture
def keys_path(tmp_path: Path) -> Path:
    path = tmp_path / KEYS_FILE_NAME
    path.write_text("{}", encoding="utf-8")
    path.chmod(KEYS_FILE_MODE)
    return path


def temp_path_of(keys_path: Path) -> Path:
    return keys_path.with_name(keys_path.name + ".tmp")


def fail_replace(source: object, target: object) -> None:
    raise OSError("disk full")


def test_a_save_that_fails_after_writing_leaves_no_temp_file(
    keys_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = KeyManager(keys_file=keys_path)
    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="disk full"):
        manager.add_key("groq", API_KEY)
    assert not temp_path_of(keys_path).exists()
    assert json.loads(keys_path.read_text(encoding="utf-8")) == {}
