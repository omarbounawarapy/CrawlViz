"""Crawl lifecycle control: start, stop, and check status.

Only one crawl runs at a time, tracked by the module-level
``_current_task``. Manual stop (POST /stop) works in two phases: it asks the
crawl to stop the way a stop condition does (a StopCrawlEvent, see
pipelines/stopping_pipeline.py), so every stage drains and flushes, and waits
for the task to end; only if the crawl does not end in time does it cancel the
task and wait for that too. Cancellation works even when a pipeline is stuck
mid-request, and the crawl's own cleanup (core/crawler.py) still runs.
"""

import asyncio
import json
import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from config import TEMPLATES_DIR, default_runtime_paths
from config.blueprint_schema import BlueprintSchemaError, validate_blueprint
from config.settings_store import load_runtime_config
from core import Crawler
from offline import build_offline_session, is_offline

logger = logging.getLogger(__name__)

# How long past the crawl's own shutdown grace a requested stop may take
# before the task is cancelled.
STOP_DRAIN_MARGIN_SECONDS = 5.0
# How long a cancelled crawl gets to run its cleanup.
CANCEL_CLEANUP_SECONDS = 10.0

router = APIRouter(tags=["run"])

_current_task: asyncio.Task | None = None
_current_crawler: Crawler | None = None


class RunRequest(BaseModel):
    templateName: str
    # Partial RuntimeConfig deep-merged over the saved settings for this run.
    overrides: dict | None = None
    seed: int | None = None


async def _run_crawler(template_name: str, config=None, seed: int | None = None) -> None:
    global _current_crawler
    try:
        if is_offline():
            session = build_offline_session(
                config or load_runtime_config(default_runtime_paths().settings_file)
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
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Crawler failed for template '%s'", template_name)
    finally:
        _current_crawler = None


@router.post("/run")
async def run_crawl(body: RunRequest):
    global _current_task

    if _current_task and not _current_task.done():
        raise HTTPException(status_code=409, detail="A crawl is already running")

    template_path = os.path.join(TEMPLATES_DIR, body.templateName)
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail=f"Template '{body.templateName}' not found")

    try:
        with open(template_path, encoding="utf-8") as f:
            validate_blueprint(json.load(f))
    except (json.JSONDecodeError, BlueprintSchemaError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        config = load_runtime_config(default_runtime_paths().settings_file, body.overrides)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    _current_task = asyncio.create_task(_run_crawler(body.templateName, config, body.seed))
    return {"started": body.templateName}


async def _ended_within(task: asyncio.Task, seconds: float) -> bool:
    """Wait for `task` to end, without raising whatever it ended with."""
    done, _ = await asyncio.wait({task}, timeout=seconds)
    return bool(done)


@router.post("/stop")
async def stop_crawl() -> dict[str, bool | str]:
    task = _current_task
    if task is None or task.done():
        return {"stopped": False, "detail": "No active crawl"}

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
    return {
        "running": running,
        "llm_calls": budget.snapshot() if budget is not None else None,
        "queues": queues,
    }
