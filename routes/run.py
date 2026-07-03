"""Crawl lifecycle control: start, stop, and check status.

Only one crawl runs at a time, tracked by the module-level
``_current_task``. Manual stop (POST /stop) hard-cancels that task,
which is why it works even when a crawl is mid-request -- unlike the
graceful StopCrawlEvent path used for automatic stop conditions (see
pipelines/stopping_pipeline.py), cancellation doesn't depend on every
pipeline noticing a flag change.
"""

import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import TEMPLATES_DIR
from core import Crawler

logger = logging.getLogger(__name__)

router = APIRouter(tags=["run"])

_current_task: asyncio.Task | None = None


class RunRequest(BaseModel):
    templateName: str


async def _run_crawler(template_name: str) -> None:
    try:
        spider = Crawler(template_name)
        await spider.start()
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Crawler failed for template '%s'", template_name)


@router.post("/run")
async def run_crawl(body: RunRequest):
    global _current_task

    if _current_task and not _current_task.done():
        raise HTTPException(status_code=409, detail="A crawl is already running")

    template_path = os.path.join(TEMPLATES_DIR, body.templateName)
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail=f"Template '{body.templateName}' not found")

    _current_task = asyncio.create_task(_run_crawler(body.templateName))
    return {"started": body.templateName}


@router.post("/stop")
async def stop_crawl():
    global _current_task

    if _current_task and not _current_task.done():
        _current_task.cancel()
        return {"stopped": True}

    return {"stopped": False, "detail": "No active crawl"}


@router.get("/status")
def crawl_status():
    running = bool(_current_task and not _current_task.done())
    return {"running": running}
