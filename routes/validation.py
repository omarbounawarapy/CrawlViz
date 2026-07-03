"""
validation.py
-------------
FastAPI router for the Validation Layer.

Exposes three read-only, bounded endpoints:
  GET /validation/tables
  GET /validation/{table}/crawls
  GET /validation/{table}/sample

All query logic is delegated to validation_db.py.
No transformation of stored values happens here.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from .validation_db import (
    fetch_all_tables,
    fetch_crawls_for_table,
    fetch_sample,
    validate_table_name,
)

router = APIRouter(prefix="/validation", tags=["validation"])


# ---------------------------------------------------------------------------
# GET /validation/tables
# ---------------------------------------------------------------------------
@router.get("/tables")
def list_tables():
    """
    Return all crawler tables present in items.db.

    Excludes SQLite internals and any table that does not match the
    crawler naming convention + required-column check.
    """
    try:
        tables = fetch_all_tables()
        return {"tables": tables}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# GET /validation/{table}/crawls
# ---------------------------------------------------------------------------
@router.get("/{table}/crawls")
def list_crawls(table: str):
    """
    Return all crawl_id groups present in `table`, newest first.

    Response shape per item:
        { crawl_id: str, count: int, last_seen: str }
    """
    try:
        validate_table_name(table)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        crawls = fetch_crawls_for_table(table)
        return {"table": table, "crawls": crawls}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# GET /validation/{table}/sample
# ---------------------------------------------------------------------------
@router.get("/{table}/sample")
def sample_rows(
    table: str,
    crawl_id: Optional[str] = Query(default=None, description="Filter by crawl_id"),
    limit: int = Query(default=20, ge=1, le=50, description="Max rows (1–50)"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
):
    """
    Return a bounded sample of extracted rows from `table`.

    All values are returned as-is from the database.
    Large field truncation / formatting is the UI's responsibility.
    """
    try:
        validate_table_name(table)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        rows = fetch_sample(table, crawl_id=crawl_id, limit=limit, offset=offset)
        return {
            "table": table,
            "crawl_id": crawl_id,
            "limit": limit,
            "offset": offset,
            "count": len(rows),
            "rows": rows,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
