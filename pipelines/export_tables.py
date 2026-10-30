"""SQLite table schema for exported items: column types, creation and key migration."""

import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


def map_export_type(export_type: str) -> str:
    return {
        "real": "REAL",
        "int": "INTEGER",
        "json": "TEXT",
        "text": "TEXT",
    }.get(export_type, "TEXT")


def ensure_table(
    cursor: sqlite3.Cursor, table_name: str, extraction_blueprint: dict[str, Any]
) -> None:
    """Create the table for a blueprint's fields if missing, then migrate its key.

    ``extraction_blueprint`` is the parsed JSON blueprint, hence ``Any`` values.
    """
    fields = extraction_blueprint.get("fields", {})
    columns = ["id TEXT", "crawl_id TEXT", "url TEXT", "created_at TEXT"]
    for field_name, spec in fields.items():
        store_type = spec.get("export_type", "text")
        sql_type = map_export_type(store_type)
        columns.append(f"{field_name} {sql_type}")
    columns.append("PRIMARY KEY (crawl_id, id)")
    sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns)})"
    cursor.execute(sql)
    migrate_primary_key(cursor, table_name)


def migrate_primary_key(cursor: sqlite3.Cursor, table_name: str) -> None:
    """Tables created before runs were isolated key rows on `id` alone, so a
    second crawl overwrote the first's rows. Rebuild them on (crawl_id, id)."""
    info = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    pk = {row[1] for row in info if row[5]}
    if pk == {"crawl_id", "id"}:
        return
    cols = ", ".join(row[1] for row in info)
    defs = ", ".join(f"{row[1]} {row[2]}" for row in info)
    legacy = f"{table_name}__legacy"
    cursor.execute(f"ALTER TABLE {table_name} RENAME TO {legacy}")
    cursor.execute(f"CREATE TABLE {table_name} ({defs}, PRIMARY KEY (crawl_id, id))")
    cursor.execute(f"INSERT OR REPLACE INTO {table_name} ({cols}) SELECT {cols} FROM {legacy}")
    cursor.execute(f"DROP TABLE {legacy}")
    logger.info("Migrated %s to primary key (crawl_id, id)", table_name)
