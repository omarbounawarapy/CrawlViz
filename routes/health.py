"""Liveness and readiness: is the process up, and can it serve a crawl.

* ``GET /health`` answers while the process runs and touches nothing, so a probe that fails
  here means the process is down or stuck.
* ``GET /ready`` answers 200 only when the app can do its work: the stored settings read
  back, and every directory a crawl writes to exists or can be created and is writable.
  Otherwise it answers 503 and names each check that failed, with what to do about it.
  It reads and never writes, so probing it leaves no files behind.

Both routes sit behind the session token and the Host and Origin checks like every other
route; there is no reason to leave them open (docs/adr/0008-subsystem-status.md).
"""

import os
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Response

from config import RuntimePaths
from config.settings_store import SettingsFileError, load_runtime_config
from crawlviz.api.schemas import HealthReply, ReadinessCheck, ReadyReply

from .config_support import get_paths

# The reply models are listed because callers read them from here as well as from the schemas.
__all__ = ["HealthReply", "ReadinessCheck", "ReadyReply", "router"]

STATUS_SERVICE_UNAVAILABLE = 503

router = APIRouter(tags=["health"])


# The directories a crawl or a settings change writes to, by the name `GET /ready` reports.
WRITE_TARGETS: tuple[tuple[str, Callable[[RuntimePaths], Path]], ...] = (
    ("settings_dir", lambda paths: paths.settings_file.parent),
    ("items_db_dir", lambda paths: paths.items_db.parent),
    ("export_dir", lambda paths: paths.export_dir),
    ("log_dir", lambda paths: paths.log_dir),
    ("debug_dir", lambda paths: paths.debug_dir),
    ("space_store_dir", lambda paths: paths.space_store_dir),
    ("presets_dir", lambda paths: paths.presets_dir),
)


def check_settings_readable(paths: RuntimePaths) -> ReadinessCheck:
    """The stored settings must load: a damaged file stops every crawl from starting."""
    try:
        load_runtime_config(paths.settings_file)
    except (SettingsFileError, OSError) as error:
        return ReadinessCheck(name="settings", ok=False, detail=str(error))
    return ReadinessCheck(name="settings", ok=True)


def check_writable(name: str, directory: Path) -> ReadinessCheck:
    """`directory`, or the nearest existing parent it would be created in, must be writable."""
    existing = directory
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    if existing.is_dir() and os.access(existing, os.W_OK | os.X_OK):
        return ReadinessCheck(name=name, ok=True)
    return ReadinessCheck(
        name=name,
        ok=False,
        detail=(
            f"The folder {existing} cannot be written to. "
            "Fix its permissions or free the disk, then check again."
        ),
    )


@router.get("/health", response_model=HealthReply)
def get_health() -> HealthReply:
    """The process is up. Nothing is read or written."""
    return HealthReply(status="ok")


@router.get(
    "/ready",
    response_model=ReadyReply,
    responses={STATUS_SERVICE_UNAVAILABLE: {"model": ReadyReply}},
)
def get_readiness(response: Response) -> ReadyReply:
    """200 when settings load and every write folder is usable; 503 with the failed checks."""
    paths = get_paths()
    checks = [
        check_settings_readable(paths),
        *(check_writable(name, locate(paths)) for name, locate in WRITE_TARGETS),
    ]
    ready = all(check.ok for check in checks)
    if not ready:
        response.status_code = STATUS_SERVICE_UNAVAILABLE
    return ReadyReply(ready=ready, checks=checks)
