"""Files the app rewrites are replaced whole or not at all."""

import json
from pathlib import Path

import pytest

from nlp import SpaceStore
from ui_bridge.event_recorder import EventRecorder
from utils import atomic_open, write_text_atomic


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

    monkeypatch.setattr("utils.jsonio.json.dumps", explode)
    with pytest.raises(OSError):
        store.record_save("bp", 5, 2)
    assert (tmp_path / "index.json").read_text() == before


def test_manifest_is_written_whole(tmp_path: Path) -> None:
    recorder = EventRecorder(tmp_path / "run")
    recorder.write_manifest({"seed": 7})
    recorder.close()
    assert json.loads((tmp_path / "run" / "manifest.json").read_text()) == {"seed": 7}
    assert not list((tmp_path / "run").glob("*.tmp"))
