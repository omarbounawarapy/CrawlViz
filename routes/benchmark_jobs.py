"""Benchmark jobs: run the whitelisted benchmark CLIs as one background
subprocess, stream its log tail, and survive a backend restart."""

import asyncio
import json
import logging
import re
import sys
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from benchmark import POLICIES

from .benchmark_paths import BENCH_DIR, RESULTS_DIR, ROOT

logger = logging.getLogger(__name__)

router = APIRouter()

LOG_TAIL = 400

_SAFE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./:-]*$")


def _path_arg(value: str) -> str:
    if not isinstance(value, str) or not _SAFE.match(value) or ".." in value:
        raise HTTPException(status_code=422, detail=f"bad path argument: {value!r}")
    resolved = (ROOT / value).resolve()
    if ROOT not in resolved.parents:
        raise HTTPException(status_code=422, detail=f"path outside the project: {value!r}")
    return value


def _word(value: str) -> str:
    if not isinstance(value, str) or not _SAFE.match(value):
        raise HTTPException(status_code=422, detail=f"bad argument: {value!r}")
    return value


# flag -> (type, validator). Only these reach the subprocess.
FlagSpecs = dict[str, Callable[[Any], Any]]

RUN_FLAGS: FlagSpecs = {
    "graph": _path_arg,
    "budget": int,
    "reps": int,
    "cascade": bool,
    "llm_all": bool,
    "no_llm": bool,
    "replay_only": bool,
    "flush_every": int,
    "provider": _word,
    "model": _word,
    "llm_cache": _path_arg,
    "runs_file": _path_arg,
    "template": _path_arg,
    "low_pct": float,
    "high_pct": float,
    "low": float,
    "high": float,
    "results_dir": _path_arg,
    "save_sequences": _path_arg,
}
ANALYZE_FLAGS: FlagSpecs = {"k": int, "test_k": int, "ndcg": bool, "no_dedupe": bool}
LABEL_FLAGS: FlagSpecs = {"graph": _path_arg, "merge": bool}
JOBS: dict[str, tuple[str, FlagSpecs]] = {
    "run": ("benchmark", RUN_FLAGS),
    "analyze": ("benchmark.analyze", ANALYZE_FLAGS),
    "label": ("benchmark.label_graph", LABEL_FLAGS),
}


def build_command(kind: str, args: dict[str, Any]) -> list[str]:
    if kind not in JOBS:
        raise HTTPException(status_code=422, detail=f"unknown job kind {kind!r}")
    module, flags = JOBS[kind]
    cmd = [sys.executable, "-m", module]
    for key, value in args.items():
        spec = flags.get(key)
        if spec is None:
            raise HTTPException(status_code=422, detail=f"flag {key!r} is not allowed for {kind}")
        flag = "--" + key.replace("_", "-")
        if spec is bool:
            if value is True:
                cmd.append(flag)
            elif value is not False:
                raise HTTPException(status_code=422, detail=f"{key} must be true or false")
            continue
        try:
            cooked = spec(value)
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=422,
                detail=f"bad value for {key}: {value!r}",
            ) from error
        cmd += [flag, str(cooked)]
    return cmd


class JobBody(BaseModel):
    kind: str
    args: dict[str, Any] = {}


LAST_JOB_FILE = BENCH_DIR / "analysis" / "last_job.json"


def expected_results(kind: str, args: dict[str, Any]) -> int | None:
    """Result files a run writes: every repeat of every baseline, plus the cascade arm."""
    if kind != "run":
        return None
    reps = int(args.get("reps", 1))
    return len(POLICIES) * reps + (reps if args.get("cascade") else 0)


class _Job:
    def __init__(self, kind: str, cmd: list[str], args: dict[str, Any] | None = None):
        self.kind, self.cmd = kind, cmd
        self.expected = expected_results(kind, args or {})
        self.started = time.time()
        self.ended: float | None = None
        self.returncode: int | None = None
        self.stopped = False
        self.log: deque[str] = deque(maxlen=LOG_TAIL)
        self.proc: asyncio.subprocess.Process | None = None

    def snapshot(self) -> dict[str, Any]:
        now = self.ended or time.time()
        new = {
            p.name
            for d in _result_dirs(self.cmd)
            for p in d.glob("*.json")
            if p.stat().st_mtime >= self.started
        }
        text = "\n".join(self.log)
        waits = len(re.findall(r"429|rate.?limit", text, re.I))
        if self.returncode is None:
            state = "running"
        elif self.stopped:
            state = "stopped"
        else:
            state = "done" if self.returncode == 0 else "failed"
        return {
            "kind": self.kind,
            "command": " ".join(self.cmd[1:]),
            "state": state,
            "returncode": self.returncode,
            "elapsed": round(now - self.started, 1),
            "expected_results": self.expected,
            "new_results": sorted(new),
            "rate_limit_mentions": waits,
            "log": list(self.log),
        }


def _result_dirs(cmd: list[str]) -> list[Path]:
    if "--results-dir" in cmd:
        return [ROOT / cmd[cmd.index("--results-dir") + 1]]
    return [RESULTS_DIR] if cmd[2] == "benchmark" else []


class _CurrentJob:
    """The one job slot; holds the task too so the pump is not garbage-collected."""

    job: _Job | None = None
    pump: "asyncio.Task[None] | None" = None


_slot = _CurrentJob()


async def _pump(job: _Job) -> None:
    proc = job.proc
    assert proc is not None and proc.stdout is not None
    async for raw in proc.stdout:
        job.log.append(raw.decode(errors="replace").rstrip())
    job.returncode = await proc.wait()
    job.ended = time.time()
    try:  # the finished job survives a backend restart
        LAST_JOB_FILE.parent.mkdir(parents=True, exist_ok=True)
        LAST_JOB_FILE.write_text(json.dumps(job.snapshot()))
    except OSError:
        logger.warning(
            "could not save the finished %s job to %s",
            job.kind,
            LAST_JOB_FILE,
            exc_info=True,
        )


@router.post("/jobs")
async def start_job(body: JobBody) -> dict[str, Any]:
    if _slot.job and _slot.job.returncode is None:
        raise HTTPException(status_code=409, detail="A benchmark job is already running")
    cmd = build_command(body.kind, body.args)
    job = _Job(body.kind, cmd, body.args)
    job.proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=ROOT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    _slot.job = job
    _slot.pump = asyncio.create_task(_pump(job))
    return job.snapshot()


@router.get("/jobs/current")
def current_job() -> dict[str, Any]:
    if _slot.job:
        return _slot.job.snapshot()
    if LAST_JOB_FILE.is_file():
        try:
            last = json.loads(LAST_JOB_FILE.read_text())
            state = "interrupted" if last["state"] == "running" else last["state"]
            return {**last, "state": state}
        except (OSError, ValueError, KeyError):
            logger.warning("could not read the last job from %s", LAST_JOB_FILE, exc_info=True)
    return {"state": "idle", "log": []}


@router.post("/jobs/stop")
async def stop_job() -> dict[str, Any]:
    job = _slot.job
    if not job or job.returncode is not None or job.proc is None:
        raise HTTPException(status_code=409, detail="No benchmark job is running")
    job.stopped = True
    job.proc.terminate()
    return job.snapshot()
