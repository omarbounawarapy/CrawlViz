"""Crawl lifecycle control: start, stop, and check status.

Only one crawl runs at a time, tracked by the module-level
``_current_task``. Manual stop (POST /stop) works in two phases: it asks the
crawl to stop the way a stop condition does (a StopCrawlEvent, see
pipelines/stop_controller.py), so every stage drains and flushes, and waits
for the task to end; only if the crawl does not end in time does it cancel the
task and wait for that too. Cancellation works even when a pipeline is stuck
mid-request, and the crawl's own cleanup (core/crawler.py) still runs.

How the last crawl ended (finished, stopped or failed, with a plain-words message for a
failure) is kept in ``_last_outcome`` and reported by GET /status.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from config import TEMPLATES_DIR, default_runtime_paths
from config.blueprint_file import load_blueprint_file
from config.blueprint_schema import Blueprint, BlueprintSchemaError, validate_blueprint
from config.settings_store import SettingsFileError, load_runtime_config, validation_errors
from config.template_names import InvalidTemplateNameError, resolve_template_path
from core import Crawler, find_preflight_problems
from crawlviz.contracts import SchemaVersionError, StoredFormatError
from offline import build_offline_session, is_offline

logger = logging.getLogger(__name__)

# How long past the crawl's own shutdown grace a requested stop may take
# before the task is cancelled.
STOP_DRAIN_MARGIN_SECONDS = 5.0
# How long a cancelled crawl gets to run its cleanup.
CANCEL_CLEANUP_SECONDS = 10.0

router = APIRouter(tags=["run"])


@dataclass(frozen=True)
class CrawlOutcome:
    """How the last crawl ended, kept after it so GET /status can report it."""

    template: str
    state: Literal["finished", "stopped", "failed"]
    error_type: str | None = None
    message: str | None = None


_current_task: asyncio.Task | None = None
_current_crawler: Crawler | None = None
_last_outcome: CrawlOutcome | None = None
_stop_requested = False


def _failed_outcome(template_name: str, error: Exception) -> CrawlOutcome:
    """A failure in plain words. The exception text stays in the log: it can hold
    URLs or keys, which must not reach the UI."""
    error_type = type(error).__name__
    return CrawlOutcome(
        template=template_name,
        state="failed",
        error_type=error_type,
        message=(
            f"The crawl of {template_name} stopped because of an internal error ({error_type}). "
            "The backend log has the details. Fix the cause, then start the crawl again."
        ),
    )


def _refuse_endpoint_overrides(overrides: dict | None) -> None:
    """Per-run overrides may not redirect an LLM provider: the request carries the API key,
    so a changed URL would send the key to whoever runs that server. Saved settings
    (PUT /config, behind the session token) are the only place endpoints change."""
    providers = (overrides or {}).get("providers")
    if isinstance(providers, dict) and "endpoints" in providers:
        raise HTTPException(
            status_code=422,
            detail="Provider endpoints cannot be changed for a single run. "
            "Change them on the Configuration page, which saves them.",
        )


def _refuse_if_running() -> None:
    if _current_task and not _current_task.done():
        raise HTTPException(status_code=409, detail="A crawl is already running")


def _read_blueprint(template_path: Path, template_name: str) -> Blueprint:
    """The validated blueprint, or a 422 that names the file and what to fix."""
    try:
        return validate_blueprint(load_blueprint_file(template_path))
    except json.JSONDecodeError as exc:
        reason = f"it is not valid JSON ({exc})"
    except OSError as exc:
        reason = f"it could not be read ({exc.strerror or exc})"
    except BlueprintSchemaError as exc:
        reason = str(exc)
    except (SchemaVersionError, StoredFormatError) as exc:
        reason = str(exc).rstrip(".")
    raise HTTPException(
        status_code=422,
        detail=f"The blueprint {template_name} cannot be used: {reason}. "
        "Fix it on the Blueprints page, then start the crawl again.",
    )


class RunRequest(BaseModel):
    templateName: str
    # Partial RuntimeConfig deep-merged over the saved settings for this run.
    overrides: dict | None = None
    seed: int | None = None


async def _run_crawler(template_name: str, config=None, seed: int | None = None) -> None:
    global _current_crawler, _last_outcome
    outcome = CrawlOutcome(template_name, "finished")
    try:
        if is_offline():
            session = build_offline_session(
                config or load_runtime_config(default_runtime_paths().settings_file),
                template_name,
            )
            spider = Crawler(
                template_name,
                config=session.config,
                seed=seed,
                llm=session.llm,
                fetcher=session.fetcher,
            )
        elif config is None:
            spider = Crawler(template_name)
        else:
            spider = Crawler(template_name, config=config, seed=seed)
        _current_crawler = spider
        await spider.start()
        if _stop_requested:
            outcome = CrawlOutcome(template_name, "stopped")
    except asyncio.CancelledError:
        outcome = CrawlOutcome(template_name, "stopped")
    except Exception as error:
        logger.exception("Crawler failed for template '%s'", template_name)
        outcome = _failed_outcome(template_name, error)
    finally:
        _current_crawler = None
        _last_outcome = outcome


@router.post("/run")
async def run_crawl(body: RunRequest):
    global _current_task, _last_outcome, _stop_requested

    _refuse_if_running()
    _refuse_endpoint_overrides(body.overrides)

    try:
        template_path = resolve_template_path(TEMPLATES_DIR, body.templateName)
    except InvalidTemplateNameError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not template_path.exists():
        raise HTTPException(status_code=404, detail=f"Template '{body.templateName}' not found")

    blueprint = _read_blueprint(template_path, body.templateName)

    paths = default_runtime_paths()
    try:
        config = load_runtime_config(paths.settings_file, body.overrides)
    except ValidationError as exc:
        problems = "; ".join(f"{e['path']}: {e['message']}" for e in validation_errors(exc))
        raise HTTPException(
            status_code=422,
            detail=f"These settings are not valid: {problems}. Correct them and start again.",
        )
    except SettingsFileError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    problems_found = await asyncio.to_thread(
        find_preflight_problems,
        blueprint.scoring.params.scoring_type,
        config,
        paths.keys_file,
        is_offline(),
    )
    if problems_found:
        raise HTTPException(status_code=409, detail=" ".join(problems_found))

    _refuse_if_running()  # another request may have started a crawl while preflight ran
    _last_outcome = None
    _stop_requested = False
    _current_task = asyncio.create_task(_run_crawler(body.templateName, config, body.seed))
    return {"started": body.templateName}


async def _ended_within(task: asyncio.Task, seconds: float) -> bool:
    """Wait for `task` to end, without raising whatever it ended with."""
    done, _ = await asyncio.wait({task}, timeout=seconds)
    return bool(done)


@router.post("/stop")
async def stop_crawl() -> dict[str, bool | str]:
    global _stop_requested
    task = _current_task
    if task is None or task.done():
        return {"stopped": False, "detail": "No active crawl"}

    _stop_requested = True

    crawler = _current_crawler
    if crawler is not None and await crawler.request_stop():
        drain_seconds = crawler.config.run.shutdown_grace + STOP_DRAIN_MARGIN_SECONDS
        if await _ended_within(task, drain_seconds):
            return {"stopped": True, "graceful": True}
        logger.warning(
            "Crawl did not end within %.0fs of a stop request; cancelling", drain_seconds
        )

    task.cancel()
    if not await _ended_within(task, CANCEL_CLEANUP_SECONDS):
        logger.error("Crawl is still running %.0fs after it was cancelled", CANCEL_CLEANUP_SECONDS)
    return {"stopped": task.done(), "graceful": False}


@router.get("/status")
def crawl_status():
    """Whether a crawl is running and, while one is, its LLM call budget (calls used, the cap, calls refused)
    and the items waiting in each pipeline queue, so the pages can show both live."""
    running = bool(_current_task and not _current_task.done())
    budget = getattr(_current_crawler, "call_budget", None) if running else None
    queues = (
        _current_crawler.queue_depths()
        if running and hasattr(_current_crawler, "queue_depths")
        else None
    )
    last = _last_outcome
    return {
        "running": running,
        "llm_calls": budget.snapshot() if budget is not None else None,
        "queues": queues,
        "last_outcome": last.state if last is not None else None,
        "last_error": (
            {"error_type": last.error_type, "message": last.message}
            if last is not None and last.state == "failed"
            else None
        ),
    }
