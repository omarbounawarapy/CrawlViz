"""A failed export flush keeps its rows so the next flush can write them."""

import sqlite3
import types
from pathlib import Path

import pytest

from core.event_broker import EventBroker
from pipelines.exporting_pipeline import ExportingPipeline

BLUEPRINT = {"extraction": {"fields": {"title": {"export_type": "text"}}}}


def _pipeline(db_path):
    pipe = ExportingPipeline("c1", "bp", BLUEPRINT, EventBroker(), db_path=db_path)
    pipe._init_db()
    return pipe


def _buffer_row(pipe, table, item_hash):
    node = types.SimpleNamespace(get_full_url=lambda: "https://example.com/a")
    pipe._buffer.append((table, node, {"title": "kept"}, BLUEPRINT["extraction"], item_hash))


def test_failed_batch_flush_keeps_the_rows_for_the_next_flush(tmp_path: Path) -> None:
    db = str(tmp_path / "items.db")
    pipe = _pipeline(db)
    _buffer_row(pipe, "t", "h1")

    pipe._flush_with_events("t")  # the table does not exist yet, so the insert fails
    assert len(pipe._buffer) == 1

    pipe._ensure_table("t", BLUEPRINT["extraction"])
    pipe._write_buffer()
    pipe.conn.close()

    rows = sqlite3.connect(db).execute("SELECT crawl_id, title FROM t").fetchall()
    assert rows == [("c1", "kept")]


def test_failed_final_flush_raises_and_keeps_the_rows(tmp_path: Path) -> None:
    pipe = _pipeline(str(tmp_path / "items.db"))
    _buffer_row(pipe, "missing", "h1")

    with pytest.raises(sqlite3.OperationalError):
        pipe._flush()

    assert len(pipe._buffer) == 1
    pipe.conn.close()
