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


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_a_reader_of_a_loose_leftover_temp_file_does_not_see_keys_saved_later(
    keys_path: Path,
) -> None:
    leftover = temp_path_of(keys_path)
    leftover.write_text("{}", encoding="utf-8")
    leftover.chmod(0o666)
    manager = KeyManager(keys_file=keys_path)
    with open(leftover, encoding="utf-8") as reader:
        manager.add_key("groq", API_KEY)
        assert API_KEY not in reader.read()
    assert json.loads(keys_path.read_text(encoding="utf-8")) == {"groq": [API_KEY]}


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_a_save_does_not_write_through_a_symlink_left_at_the_temp_path(
    keys_path: Path, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text("{}", encoding="utf-8")
    temp_path_of(keys_path).symlink_to(elsewhere)
    KeyManager(keys_file=keys_path).add_key("groq", API_KEY)
    assert API_KEY not in elsewhere.read_text(encoding="utf-8")
    assert json.loads(keys_path.read_text(encoding="utf-8")) == {"groq": [API_KEY]}
