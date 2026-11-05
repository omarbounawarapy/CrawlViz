"""Files the app rewrites are replaced whole or not at all."""

import json
import os
import stat
from pathlib import Path

import pytest

from crawlviz.nlp import SpaceStore
from crawlviz.shared import atomic_open, write_text_atomic
from ui_bridge.event_recorder import EventRecorder


def test_write_text_atomic_replaces_the_file_and_leaves_no_temp(tmp_path: Path) -> None:
    target = tmp_path / "out" / "file.json"
    write_text_atomic(target, "first")
    write_text_atomic(target, "second")
    assert target.read_text() == "second"
    assert [p.name for p in target.parent.iterdir()] == ["file.json"]


def test_failed_write_keeps_the_old_file_and_removes_the_temp(tmp_path: Path) -> None:
    target = tmp_path / "file.json"
    target.write_text("old")
    with pytest.raises(RuntimeError), atomic_open(target) as handle:
        handle.write("half of the new con")
        raise RuntimeError("disk full")
    assert target.read_text() == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["file.json"]


def test_binary_mode_writes_bytes(tmp_path: Path) -> None:
    target = tmp_path / "file.bin"
    with atomic_open(target, "wb") as handle:
        handle.write(b"\x00\x01")
    assert target.read_bytes() == b"\x00\x01"


def test_space_index_write_failure_keeps_the_previous_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SpaceStore(str(tmp_path), model_name="m")
    store.record_save("bp", 2, 1)
    before = (tmp_path / "index.json").read_text()

    def explode(*args: object, **kwargs: object) -> str:
        raise OSError("disk full")

    monkeypatch.setattr("crawlviz.shared.jsonio.json.dumps", explode)
    with pytest.raises(OSError):
        store.record_save("bp", 5, 2)
    assert (tmp_path / "index.json").read_text() == before


def test_manifest_is_written_whole(tmp_path: Path) -> None:
    recorder = EventRecorder(tmp_path / "run")
    recorder.write_manifest({"seed": 7})
    recorder.close()
    assert json.loads((tmp_path / "run" / "manifest.json").read_text()) == {"seed": 7}
    assert not list((tmp_path / "run").glob("*.tmp"))


def temp_path_of(target: Path) -> Path:
    return target.with_name(target.name + ".tmp")


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_a_symlink_left_at_the_temp_path_is_not_written_through(tmp_path: Path) -> None:
    target = tmp_path / "file.json"
    elsewhere = tmp_path / "elsewhere.txt"
    elsewhere.write_text("untouched")
    temp_path_of(target).symlink_to(elsewhere)
    write_text_atomic(target, "new content")
    assert elsewhere.read_text() == "untouched"
    assert target.read_text() == "new content"


@pytest.mark.skipif(os.name == "nt", reason="POSIX file semantics")
def test_a_reader_holding_a_leftover_temp_file_does_not_see_new_content(tmp_path: Path) -> None:
    target = tmp_path / "file.json"
    leftover = temp_path_of(target)
    leftover.write_text("old")
    with open(leftover, encoding="utf-8") as reader:
        write_text_atomic(target, "new secret")
        assert "new secret" not in reader.read()
    assert target.read_text() == "new secret"


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_file_mode_sets_the_permissions_whatever_the_umask(tmp_path: Path) -> None:
    target = tmp_path / "file.json"
    old_umask = os.umask(0)
    try:
        with atomic_open(target, file_mode=0o600) as handle:
            handle.write("{}")
    finally:
        os.umask(old_umask)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
