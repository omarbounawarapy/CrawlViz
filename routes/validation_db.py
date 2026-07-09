"""
validation_db.py
----------------
Minimal read-only SQLite utility for the Validation Layer.

Responsibilities:
    - Open a per-request connection to items.db.
    - Execute bounded, scoped, read-only queries.
    - Return rows as plain dicts.

Constraints:
    - Standard library only (sqlite3).
    - No global connection, no ORM, no dynamic SQL builder.
    - Table names validated via allowlist before interpolation.
    - All queries are read-only and LIMIT-bounded.
"""

import re
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager

from config import ITEMS_DB_PATH

# =========================================================
# TABLE-NAME VALIDATION
# =========================================================
# Crawler tables follow the pattern: <domain_with_underscores>_<blueprint_id>
# Domain part: alphanumeric + underscores, no leading/trailing underscores.
# Blueprint id: alphanumeric + underscores.
# Kept strict so no user-supplied string can escape the identifier slot.
_TABLE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_]{1,127}$")

# SQLite internal / metadata tables that must never be exposed.
_BLOCKED_TABLES = frozenset(
    {
        "sqlite_master",
        "sqlite_sequence",
        "sqlite_stat1",
        "sqlite_stat2",
        "sqlite_stat3",
        "sqlite_stat4",
        "sqlite_temp_master",
    }
)

# Columns every crawler table is guaranteed to have (from exporting_pipeline.py).
_REQUIRED_CRAWLER_COLUMNS = frozenset({"id", "crawl_id", "url", "created_at"})


def validate_table_name(table: str) -> str:
    """Validate `table` as a safe, recognized crawler table name.

    Returns:
        The validated name, unchanged, so callers can use it directly.

    Raises:
        ValueError: If `table` doesn't match the naming pattern, or is
            a blocked SQLite internal table.
    """
    if not _TABLE_NAME_RE.match(table):
        raise ValueError(f"Invalid table name: {table!r}")
    if table.lower() in _BLOCKED_TABLES:
        raise ValueError(f"Blocked table name: {table!r}")
    return table


# =========================================================
# CONNECTION CONTEXT MANAGER
# =========================================================
@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Yield a short-lived, read-optimized SQLite connection.

    WAL mode ensures reads do not block concurrent writes. The
    connection is always closed on exit.
    """
    conn = sqlite3.connect(f"file:{ITEMS_DB_PATH}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        # WAL is a database-level setting; setting it here is a no-op if
        # already enabled by the writer, but harmless and explicit.
        conn.execute("PRAGMA journal_mode=WAL;")
        yield conn
    finally:
        conn.close()


# =========================================================
# QUERY HELPERS -- ALL READ-ONLY, ALL BOUNDED
# =========================================================

def fetch_all_tables() -> list[str]:
    """Return names of all user-created tables that look like crawler tables.

    A table qualifies when:
        1. It is not in the SQLite internal tables blocklist.
        2. Its name matches the crawler naming pattern.
        3. It contains the four mandatory crawler columns.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        ).fetchall()

    tables = []
    for row in rows:
        name = row["name"]
        if name.lower() in _BLOCKED_TABLES:
            continue
        if not _TABLE_NAME_RE.match(name):
            continue
        # Verify mandatory columns exist (lightweight schema check).
        if _has_required_columns(name):
            tables.append(name)

    return tables


def _has_required_columns(table: str) -> bool:
    """Return True when `table` contains all mandatory crawler columns.

    Opens its own connection to keep each helper self-contained.
    """
    try:
        with get_connection() as conn:
            cursor = conn.execute(f"PRAGMA table_info({table});")  # safe: already regex-checked
            cols = {r["name"] for r in cursor.fetchall()}
        return _REQUIRED_CRAWLER_COLUMNS.issubset(cols)
    except Exception:
        return False


def fetch_crawls_for_table(table: str) -> list[dict]:
    """Return aggregated crawl_id records for `table`, newest first.

    Returns:
        A list of ``{"crawl_id": str, "count": int, "last_seen": str}`` dicts.
    """
    validate_table_name(table)

    sql = f"""
        SELECT
            crawl_id,
            COUNT(*) AS count,
            MAX(created_at) AS last_seen
        FROM {table}
        GROUP BY crawl_id
        ORDER BY last_seen DESC;
    """  # table name safe: validated above

    with get_connection() as conn:
        rows = conn.execute(sql).fetchall()

    return [dict(r) for r in rows]


def fetch_sample(
    table: str,
    crawl_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """Return a bounded sample of rows from `table`.

    Args:
        table: A validated crawler table name.
        crawl_id: Optional filter; if None, every crawl_id is included.
        limit: Capped at 50 (API-level enforcement mirrored here).
        offset: Pagination offset.
    """
    validate_table_name(table)

    # Hard-cap regardless of what the caller requests.
    limit = min(max(1, limit), 50)
    offset = max(0, offset)

    if crawl_id is not None:
        sql = f"""
            SELECT *
            FROM {table}
            WHERE crawl_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?;
        """
        params = (crawl_id, limit, offset)
    else:
        sql = f"""
            SELECT *
            FROM {table}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?;
        """
        params = (limit, offset)

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [dict(r) for r in rows]
