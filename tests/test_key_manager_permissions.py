"""keys.json is kept readable by its owner only."""

import json
import logging
import os
import stat
from pathlib import Path

import pytest

from infrastructure.key_manager import KeyManager

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")


def mode_of(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def write_keys(path: Path, mode: int) -> None:
    path.write_text(json.dumps({"groq": ["k1"]}), encoding="utf-8")
    path.chmod(mode)


def test_a_world_readable_keys_file_is_restricted_on_load(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    keys_file = tmp_path / "keys.json"
    write_keys(keys_file, 0o644)
    with caplog.at_level(logging.WARNING):
        KeyManager(keys_file=keys_file)
    assert mode_of(keys_file) == 0o600
    assert "readable by other users" in caplog.text


def test_an_owner_only_keys_file_logs_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    keys_file = tmp_path / "keys.json"
    write_keys(keys_file, 0o600)
    with caplog.at_level(logging.WARNING):
        KeyManager(keys_file=keys_file)
    assert "readable by other users" not in caplog.text


def test_save_over_a_loose_temp_file_still_writes_owner_only(tmp_path: Path) -> None:
    keys_file = tmp_path / "keys.json"
    write_keys(keys_file, 0o600)
    manager = KeyManager(keys_file=keys_file)
    leftover = tmp_path / "keys.json.tmp"
    leftover.write_text("{}", encoding="utf-8")
    leftover.chmod(0o666)
    manager.save()
    assert mode_of(keys_file) == 0o600
