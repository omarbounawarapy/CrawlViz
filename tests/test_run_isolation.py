"""Run isolation: a stored vector space is keyed by (blueprint, model) and
read-only unless opted in; items.db rows are keyed by (crawl_id, hash)."""
import asyncio
import sqlite3
import types

import numpy as np

from core.event_broker import EventBroker
from nlp import SpaceStore, VectorSpace
from pipelines.exporting_pipeline import ExportingPipeline
from services.nlp_service import NLPService


def _space(version=3):
    sp = VectorSpace(dim=4)
    sp.add_vector("a", np.array([1, 0, 0, 0], dtype=np.float32), {"type": "seed", "text": "x"})
    sp.add_vector("b", np.array([0, 1, 0, 0], dtype=np.float32), {"n": np.int64(2)})
    sp.version = version
    return sp


def test_space_round_trips_without_pickle(tmp_path):
    path = str(tmp_path / "latest")
    _space().save(path)
    assert not list(tmp_path.glob("*.pkl"))
    loaded = VectorSpace(dim=4)
    loaded.load(path)
    assert loaded.version == 3 and [e.key for e in loaded.entries] == ["a", "b"]
    assert loaded.entries[1].metadata == {"n": 2}
    assert np.allclose(loaded.get_matrix(), _space().get_matrix())


def test_store_is_keyed_by_model(tmp_path):
    a = SpaceStore(str(tmp_path), model_name="model-a")
    b = SpaceStore(str(tmp_path), model_name="model-b")
    _space().save(a.space_path("bp"))
    assert a.exists("bp") and not b.exists("bp")
    a.record_save("bp", 2, 3)
    assert a.get_metadata("bp")["version"] == 3 and b.get_metadata("bp") is None


def _service(tmp_path, persist):
    svc = NLPService.__new__(NLPService)
    svc.blueprint_id = "bp"
    svc.store = SpaceStore(str(tmp_path), model_name="m")
    svc.persist_space = persist
    svc.space = _space(version=1)
    return svc


def test_stored_space_is_read_only_unless_persisted(tmp_path):
    svc = _service(tmp_path, persist=False)
    svc.save_space()  # first save bootstraps the store
    svc.space.version = 9
    svc.save_space()
    fresh = VectorSpace(dim=4)
    fresh.load(svc.store.space_path("bp"))
    assert fresh.version == 1  # a second run starts from the same version

    svc.persist_space = True
    svc.save_space()
    fresh.load(svc.store.space_path("bp"))
    assert fresh.version == 9


def _export(db, crawl_id, title):
    asyncio.run(_aexport(db, crawl_id, title))


async def _aexport(db, crawl_id, title):
    bp = {"extraction": {"fields": {"title": {"export_type": "text"}}}}
    pipe = ExportingPipeline(crawl_id, "bp", bp, EventBroker(), db_path=db)
    pipe._init_db()
    node = types.SimpleNamespace(get_full_url=lambda: "https://example.com/a")
    pipe._ensure_table("t", bp["extraction"])
    pipe._insert_row("t", node, {"title": title}, bp["extraction"], "samehash")
    pipe.conn.commit()
    pipe.conn.close()


def test_two_crawls_keep_their_rows(tmp_path):
    db = str(tmp_path / "items.db")
    _export(db, "c1", "one")
    _export(db, "c2", "two")
    rows = sqlite3.connect(db).execute("SELECT crawl_id, title FROM t ORDER BY 1").fetchall()
    assert rows == [("c1", "one"), ("c2", "two")]


def test_legacy_table_is_migrated(tmp_path):
    db = str(tmp_path / "items.db")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE t (id TEXT PRIMARY KEY, crawl_id TEXT, url TEXT, created_at TEXT, title TEXT)")
    con.execute("INSERT INTO t VALUES ('samehash','old','u','now','legacy')")
    con.commit(); con.close()
    _export(db, "c2", "new")
    rows = sqlite3.connect(db).execute("SELECT crawl_id, title FROM t ORDER BY 1").fetchall()
    assert rows == [("c2", "new"), ("old", "legacy")]
