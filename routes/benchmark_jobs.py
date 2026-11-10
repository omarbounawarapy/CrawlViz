"""Benchmark jobs: run the whitelisted benchmark CLIs as one background
subprocess, stream its log tail, and survive a backend restart."""

import asyncio
import contextlib
import json
import logging
import re
import sys
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from benchmark import POLICIES
from config import TEMPLATES_DIR
from config.redaction import redact_text

from .benchmark_paths import BENCH_DIR, DATA_DIR, RESULTS_DIR, ROOT

logger = logging.getLogger(__name__)

router = APIRouter()

LOG_TAIL = 400
# A subprocess line longer than this is cut before it is masked, so one huge line cannot
# hold the event loop in the masking regexes or fill the saved log.
MAX_LOG_LINE_CHARS = 4096
LOG_LINE_CUT_MARK = " ...[line cut]"
OUTPUT_FAILED_LOG_LINE = "[the job output could not be read, so the job was stopped]"

_SAFE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./:-]*$")


def _path_inside(value: str, *allowed_dirs: Path) -> str:
    """``value`` (relative to the project root) when it resolves inside one of ``allowed_dirs``.

    Resolving follows symlinks, so a link cannot lead out of the directory."""
    if not isinstance(value, str) or not _SAFE.match(value) or ".." in value:
        raise HTTPException(status_code=422, detail=f"bad path argument: {value!r}")
    resolved = (ROOT / value).resolve()
    if not any(resolved.is_relative_to(directory.resolve()) for directory in allowed_dirs):
        allowed = ", ".join(str(d.relative_to(ROOT)) for d in allowed_dirs)
        raise HTTPException(status_code=422, detail=f"path {value!r} must be inside {allowed}")
    return value


def _graph_arg(value: str) -> str:
    """A frozen graph file in benchmark/data."""
    return _path_inside(value, DATA_DIR)


def _template_arg(value: str) -> str:
    """A blueprint in the templates directory."""
    return _path_inside(value, TEMPLATES_DIR)


def _output_arg(value: str) -> str:
    """A file or folder a job writes: only benchmark/data and benchmark/results may be written."""
    return _path_inside(value, DATA_DIR, RESULTS_DIR)


def _word(value: str) -> str:
    if not isinstance(value, str) or not _SAFE.match(value):
        raise HTTPException(status_code=422, detail=f"bad argument: {value!r}")
    return value


# flag -> (type, validator). Only these reach the subprocess.
FlagSpecs = dict[str, Callable[[Any], Any]]

RUN_FLAGS: FlagSpecs = {
    "graph": _graph_arg,
    "budget": int,
    "reps": int,
    "cascade": bool,
    "llm_all": bool,
    "no_llm": bool,
    "replay_only": bool,
    "flush_every": int,
    "provider": _word,
    "model": _word,
    "llm_cache": _output_arg,
    "runs_file": _output_arg,
    "template": _template_arg,
    "low_pct": float,
    "high_pct": float,
    "low": float,
    "high": float,
    "results_dir": _output_arg,
    "save_sequences": _output_arg,
}
ANALYZE_FLAGS: FlagSpecs = {"k": int, "test_k": int, "ndcg": bool, "no_dedupe": bool}
LABEL_FLAGS: FlagSpecs = {"graph": _graph_arg, "merge": bool}
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


def _log_line(raw: bytes, was_cut: bool = False) -> str:
    """One subprocess output line, masked and kept to the limit; a cut line is marked.

    The line is cut before it is masked (the cost) and after (masking can lengthen it).
    `was_cut` says the reader already dropped the end of the line.
    """
    line = raw.decode(errors="replace").rstrip()
    masked = redact_text(line[:MAX_LOG_LINE_CHARS])
    if was_cut or len(line) > MAX_LOG_LINE_CHARS or len(masked) > MAX_LOG_LINE_CHARS:
        return masked[:MAX_LOG_LINE_CHARS] + LOG_LINE_CUT_MARK
    return masked


async def _skip_rest_of_line(stream: asyncio.StreamReader) -> None:
    """Drop the input up to and including the next newline, or to the end of the stream."""
    while True:
        try:
            await stream.readuntil(b"\n")
        except asyncio.LimitOverrunError as overrun:
            await stream.readexactly(overrun.consumed)
        except asyncio.IncompleteReadError:
            return
        else:
            return


async def _read_log_lines(stream: asyncio.StreamReader) -> AsyncIterator[tuple[bytes, bool]]:
    """Each line of `stream` with a flag that says its end was dropped.

    ``async for line in stream`` raises ``ValueError`` on a line over the reader's limit
    (64 KiB) and loses the line, which would stop the pump. A line over the limit is
    kept up to the limit, its end is skipped and reading goes on with the next line.
    """
    while True:
        try:
            yield await stream.readuntil(b"\n"), False
        except asyncio.IncompleteReadError as end_of_stream:
            if end_of_stream.partial:
                yield end_of_stream.partial, False
            return
        except asyncio.LimitOverrunError as overrun:
            head = await stream.readexactly(overrun.consumed)
            await _skip_rest_of_line(stream)
            yield head, True


async def _pump(job: _Job) -> None:
    proc = job.proc
    assert proc is not None and proc.stdout is not None
    try:
        async for raw, was_cut in _read_log_lines(proc.stdout):
            # The subprocess may print a failed request with its key; the log is shown and saved.
            job.log.append(_log_line(raw, was_cut))
    except Exception:
        # Nobody reads the pipe now, so the child would block on a full pipe and the job
        # would stay "running" and refuse every new job. Stop it and end the job below.
        logger.exception("could not read the output of the %s job; stopping it", job.kind)
        job.log.append(OUTPUT_FAILED_LOG_LINE)
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
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
