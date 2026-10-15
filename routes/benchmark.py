"""Benchmark area of the UI: read the experiment's files, annotate the audit,
and run the benchmark CLIs as one background job.

Everything is file-based and lives under ``benchmark/``. Reads never call an
LLM. The only writes are the annotator TSVs (``audit_ui_<annotator>.tsv``,
never ``audit_filled.tsv``) and whatever the whitelisted CLIs themselves write.
"""

import asyncio
import csv
import json
import math
import re
import sys
import time
from collections import deque
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from benchmark import audit as audit_mod
from benchmark.analyze import (
    by_policy, dedupe_records, efficiency, harvest_at, mean_ci,
    validity_counts,
)
from benchmark.graph import FrozenGraph
from benchmark.graph_stats import stats as graph_stats
from benchmark.results import RunRecord

router = APIRouter(prefix="/benchmark", tags=["benchmark"])

ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = ROOT / "benchmark"
DATA_DIR = BENCH_DIR / "data"
RESULTS_DIR = BENCH_DIR / "results"
LOG_TAIL = 400

PROTOCOL_FILE = BENCH_DIR / "PROTOCOL.md"


def _section(text: str, number: str) -> str:
    """The body of '## <number>. ...' up to the next '## ' heading."""
    m = re.search(rf"^## {re.escape(number)}\.? .*?$(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1) if m else ""


def _cells(line: str) -> list[str]:
    return [c.strip().replace("`", "") for c in line.strip().strip("|").split("|")]


def read_protocol() -> dict:
    """Hypotheses, arms, budgets, models and amendments, read from PROTOCOL.md itself."""
    if not PROTOCOL_FILE.is_file():
        return {"hypotheses": [], "arms": [], "budgets": [], "models": [], "primary_metric": "",
                "amendments": []}
    text = PROTOCOL_FILE.read_text()
    hypotheses = []
    for line in _section(text, "1").splitlines():
        c = _cells(line) if line.startswith("|") else []
        if len(c) >= 3 and re.fullmatch(r"H\d", c[0]):
            hypotheses.append({"id": c[0], "text": c[1], "comparison": c[2]})
    arms = []
    sec5 = _section(text, "5")
    for line in sec5.splitlines():
        c = _cells(line) if line.startswith("|") else []
        if len(c) >= 4 and re.match(r"\d+", c[1]):
            arms.append({"arm": c[0], "repeats": c[1], "scopes": c[2], "llm": c[3]})
    budgets = [int(b) for b in re.findall(r"\d+", (re.search(r"Budgets[^:]*:\s*([^.]*)\.", sec5) or [None, ""])[1])]
    models = []
    for line in _section(text, "6").splitlines():
        c = _cells(line) if line.startswith("|") else []
        if len(c) == 3 and c[0] not in ("Role", "") and not set(c[0]) <= set("-"):
            models.append({"role": c[0], "provider": c[1], "model": c[2]})
    metric = re.search(r"^harvest@30[^\n]*(?:\n[^\n]+)*", _section(text, "2").strip(), re.M)
    tail = text.split("\n## Amendments", 1)[1] if "\n## Amendments" in text else ""
    parts = re.split(r"^\*\*(\d{4}-\d{2}-\d{2}[^*]*)\*\*", tail, flags=re.M)
    amendments = [{"title": parts[k].strip().rstrip("."), "body": parts[k + 1].strip().replace("`", "")}
                  for k in range(1, len(parts) - 1, 2)]
    return {
        "hypotheses": hypotheses, "arms": arms, "budgets": budgets, "models": models,
        "primary_metric": " ".join(metric.group(0).split()).replace("`", "") if metric else "",
        "amendments": amendments,
    }


def _nan(v):
    return None if isinstance(v, float) and math.isnan(v) else v


def _file(name: str, suffix: str) -> Path:
    """A file directly inside benchmark/data, by plain name."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or not name.endswith(suffix):
        raise HTTPException(status_code=422, detail=f"bad file name: {name!r}")
    return DATA_DIR / name


# ── graphs ───────────────────────────────────────────────────────────────────

_graph_cache: dict[str, tuple[float, FrozenGraph]] = {}


def _graph(name: str) -> FrozenGraph:
    path = _file(name, ".json")
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"graph {name!r} not found")
    mtime = path.stat().st_mtime
    hit = _graph_cache.get(name)
    if hit and hit[0] == mtime:
        return hit[1]
    graph = FrozenGraph.load(path)
    _graph_cache[name] = (mtime, graph)
    return graph


def _graph_names() -> list[str]:
    """Graph files that carry pages (the raw scrape and caches are not graphs)."""
    out = []
    for p in sorted(DATA_DIR.glob("*.json")):
        try:
            with p.open("rb") as f:
                head = f.read(65536)
        except OSError:
            continue
        if b'"pages"' in head:
            out.append(p.name)
    return out


# ── runs ─────────────────────────────────────────────────────────────────────

def _records() -> list[tuple[str, RunRecord]]:
    out = []
    for p in sorted(RESULTS_DIR.glob("*.json")):
        try:
            out.append((p.stem, RunRecord.from_json(json.loads(p.read_text()))))
        except (OSError, ValueError, TypeError):
            continue
    return out


def _summary(name: str, r: RunRecord) -> dict:
    found = sum(1 for v in r.labels if v >= 1)
    return {
        "name": name, "graph": r.graph, "policy": r.policy, "rep": r.rep, "budget": r.budget,
        "valid": r.valid, "status": r.status, "replay": r.replay, "fetched": len(r.sequence),
        "found": found, "found_label2": sum(1 for v in r.labels if v == 2),
        "harvest30": harvest_at(r.labels, 30) if r.labels else None,
        "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
        "llm_calls": r.llm_calls, "llm_replayed": r.llm_replayed,
        "wall_seconds": r.wall_seconds, "replay_misses": r.replay_misses,
        "problems": r.problems,
        "short": len(r.sequence) < 0.9 * r.budget if r.budget else False,
    }


@router.get("/runs")
def list_runs():
    return [_summary(n, r) for n, r in _records()]


@router.get("/runs/{name}")
def get_run(name: str):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise HTTPException(status_code=422, detail="bad run name")
    path = RESULTS_DIR / f"{name}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="run not found")
    record = RunRecord.from_json(json.loads(path.read_text()))
    return {**_summary(name, record), "sequence": record.sequence, "labels": record.labels,
            "manifest": record.manifest, "settings": record.settings}


@router.get("/curves")
def get_curves(min_grade: int = Query(1, ge=1, le=2), max_k: int = Query(100, ge=1, le=500),
               budget: int | None = None):
    records = [r for _, r in _records() if budget is None or r.budget == budget]
    records = dedupe_records(records, DATA_DIR)
    groups = by_policy(records)
    series = {}
    # No curve beyond the longest run: past it the value is a constant, not a measurement.
    max_k = min(max_k, max((len(r.sequence) for runs in groups.values() for r in runs), default=1))
    for policy, runs in groups.items():
        points = []
        for k in range(1, max_k + 1):
            mean, ci = mean_ci([harvest_at(r.labels, k, min_grade) for r in runs])
            points.append({"k": k, "mean": _nan(mean), "ci95": _nan(ci)})
        eff = [efficiency(r) for r in runs]

        def avg(vals):
            vals = [v for v in vals if not math.isnan(v) and not math.isinf(v)]
            return sum(vals) / len(vals) if vals else None
        series[policy] = {
            "runs": len(runs), "points": points,
            "short": sum(1 for r in runs if r.budget and len(r.sequence) < 0.9 * r.budget),
            "tokens": sum(r.input_tokens + r.output_tokens for r in runs) / len(runs),
            "rel_per_call": avg([e[0] for e in eff]),
            "rel_per_1k_tokens": avg([e[1] for e in eff]),
        }
    return {"min_grade": min_grade, "series": series, "validity": validity_counts(records)}


# ── overview and graph ───────────────────────────────────────────────────────

@router.get("/overview")
def overview():
    graphs = {}
    for name in _graph_names():
        try:
            s = graph_stats(_graph(name))
        except Exception:  # unreadable or half-written graph file
            continue
        graphs[name] = {**{k: s[k] for k in ("pages", "edges", "absent_links", "reachable",
                                              "out_degree", "labels", "relevant_unreachable")},
                        "depth": [{"depth": d, **row} for d, row in s["relevant_per_depth"].items()]}
    key = DATA_DIR / "audit_key.json"
    return {"protocol": read_protocol(), "graphs": graphs,
            "audit": _audit_result(key, DATA_DIR / "audit_filled.tsv") if key.is_file() else None,
            "runs": len(_records())}


@router.get("/graph")
def get_graph(name: str = "isi.json", max_depth: int = Query(1, ge=0, le=6),
              limit: int = Query(400, ge=10, le=3000)):
    """Seed-centred subgraph as a breadth-first spanning tree (what the crawl graph view draws).

    Pages up to ``max_depth``, relevant pages first. ``parent`` is the page each
    one was first reached from; links that are not tree edges are counted in
    ``cross_links`` and not drawn.
    """
    from collections import deque

    graph = _graph(name)
    depth, parent = {graph.seed: 0}, {graph.seed: None}
    queue = deque([graph.seed])
    while queue:
        n = queue.popleft()
        for link in graph.pages[n]["links"]:
            t = link["to"]
            if t in graph.pages and t not in depth:
                depth[t], parent[t] = depth[n] + 1, n
                queue.append(t)
    ranked = sorted((n for n, d in depth.items() if d <= max_depth),
                    key=lambda n: (-graph.label(n), depth[n], n))
    keep = set(ranked[:limit])
    # A kept page needs its chain of ancestors, or the tree falls apart.
    for n in list(keep):
        a = parent[n]
        while a is not None and a not in keep:
            keep.add(a)
            a = parent[a]
    nodes = [{"id": n, "parent": parent[n], "title": graph.pages[n].get("title") or n,
              "label": graph.label(n), "depth": depth[n], "out": len(graph.pages[n]["links"])}
             for n in sorted(keep, key=lambda n: (depth[n], n))]
    tree = sum(1 for n in keep if parent[n] is not None)
    all_links = sum(1 for n in keep for link in graph.pages[n]["links"] if link["to"] in keep)
    return {"name": name, "seed": graph.seed, "topic": graph.topic, "total": len(graph.pages),
            "shown": len(nodes), "cross_links": all_links - tree, "nodes": nodes}


@router.get("/page")
def get_page(name: str, graph: str = "isi.json"):
    g = _graph(graph)
    page = g.pages.get(name)
    if page is None:
        raise HTTPException(status_code=404, detail="page not in graph")
    return {"id": name, "title": page.get("title"), "label": g.label(name),
            "text": (page.get("text") or "")[:3000], "links": page["links"][:60]}


@router.get("/estimate")
def estimate(budget: int = Query(50, ge=1)):
    """Tokens per fetched page of each recorded LLM arm, from the result files (none if never run)."""
    per: dict[str, list[float]] = {}
    for _, r in _records():
        tokens = r.input_tokens + r.output_tokens
        if r.replay or not r.valid or not r.sequence or not tokens:
            continue
        arm = "cascade" if r.policy.startswith("cascade") else r.policy
        per.setdefault(arm, []).append(tokens / len(r.sequence))
    return {"budget": budget, "arms": {
        arm: {"tokens_per_page": sum(v) / len(v), "runs": len(v), "tokens_for_budget": sum(v) / len(v) * budget}
        for arm, v in per.items()}}


# ── audit annotation ─────────────────────────────────────────────────────────

ANNOTATORS = ("1", "2")
SECOND_ANNOTATOR_ITEMS = 50  # PROTOCOL.md section 8.4: the first 50 ids of the same TSV


def _audit_paths(annotator: str) -> Path:
    if annotator not in ANNOTATORS:
        raise HTTPException(status_code=422, detail="annotator must be 1 or 2")
    return DATA_DIR / f"audit_ui_{annotator}.tsv"


def _audit_rows(annotator: str = "1") -> list[dict]:
    path = DATA_DIR / "audit.tsv"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="no audit sample; run `benchmark.audit sample`")
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    return rows[:SECOND_ANNOTATOR_ITEMS] if annotator == "2" else rows


def _labels_of(path: Path) -> dict[str, int]:
    return audit_mod.read_labels(path) if path.is_file() else {}


@router.get("/audit")
def get_audit(annotator: str = "1"):
    """The sample for a human. The judge's label is never sent (blind audit)."""
    labels = _labels_of(_audit_paths(annotator))
    items = [{"id": r["id"], "title": r["title"], "excerpt": r["excerpt"],
              "human_label": labels.get(r["id"])} for r in _audit_rows(annotator)]
    return {"annotator": annotator, "items": items,
            "done": sum(1 for i in items if i["human_label"] is not None)}


class LabelBody(BaseModel):
    human_label: int | None


@router.put("/audit/{item_id}")
def put_audit(item_id: str, body: LabelBody, annotator: str = "1"):
    if body.human_label not in (None, 0, 1, 2):
        raise HTTPException(status_code=422, detail="human_label must be 0, 1, 2 or null")
    path = _audit_paths(annotator)
    rows = _audit_rows(annotator)
    if item_id not in {r["id"] for r in rows}:
        raise HTTPException(status_code=404, detail="unknown item id")
    labels = _labels_of(path)
    if body.human_label is None:
        labels.pop(item_id, None)
    else:
        labels[item_id] = body.human_label
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["id", "title", "excerpt", "human_label"])
        for r in rows:
            w.writerow([r["id"], r["title"], r["excerpt"], labels.get(r["id"], "")])
    tmp.replace(path)
    return {"id": item_id, "human_label": body.human_label, "done": len(labels)}


def _audit_result(key_path: Path, tsv: Path, total: int | None = None, other: Path | None = None) -> dict | None:
    key = json.loads(key_path.read_text())
    human = _labels_of(tsv)
    ids = sorted((i for i in human if i in key["items"]), key=int)
    if not ids:
        return None
    pairs = [(key["items"][i]["judge_label"], human[i]) for i in ids]
    bp = audit_mod.binary(pairs)
    counts = {int(g): n for g, n in key["graph_label_counts"].items()}
    prec, rec = audit_mod.per_class(bp, (1,))[1]
    return {
        "n": len(pairs), "sampled": total or len(key["items"]),
        "confusion": audit_mod.confusion(pairs, (0, 1, 2)),
        "confusion_binary": audit_mod.confusion(bp, (0, 1)),
        "agreement": _nan(audit_mod.agreement(pairs)),
        "kappa": _nan(audit_mod.kappa(pairs)),
        "agreement_binary": _nan(audit_mod.agreement(bp)),
        "kappa_binary": _nan(audit_mod.kappa(bp)),
        "kappa_ci": [_nan(v) for v in audit_mod.bootstrap_ci(pairs, audit_mod.kappa)],
        "relevant_precision": _nan(prec), "relevant_recall": _nan(rec),
        "reweighted": _nan(audit_mod.reweighted_agreement(pairs, counts)[0]),
        "human_vs_annotator1": _human_pair(human, other),
    }


def _human_pair(human: dict[str, int], other: Path | None) -> dict | None:
    """Annotator 2 against annotator 1 on the ids both labelled (PROTOCOL.md section 8.4)."""
    first = _labels_of(other) if other else {}
    both = sorted(set(human) & set(first), key=int)
    if not both:
        return None
    pairs = [(first[i], human[i]) for i in both]
    return {"n": len(pairs), "agreement": _nan(audit_mod.agreement(pairs)),
            "kappa": _nan(audit_mod.kappa(pairs)),
            "agreement_binary": _nan(audit_mod.agreement(audit_mod.binary(pairs))),
            "kappa_binary": _nan(audit_mod.kappa(audit_mod.binary(pairs)))}


@router.post("/audit/score")
def score_audit(annotator: str = "1", source: str = "ui"):
    """Judge against a human. ``source=filled`` scores the original audit_filled.tsv."""
    key = DATA_DIR / "audit_key.json"
    if not key.is_file():
        raise HTTPException(status_code=404, detail="no audit key")
    tsv = DATA_DIR / "audit_filled.tsv" if source == "filled" else _audit_paths(annotator)
    second = annotator == "2" and source != "filled"
    result = _audit_result(
        key, tsv, SECOND_ANNOTATOR_ITEMS if second else None,
        _audit_paths("1") if second else None,
    )
    if result is None:
        raise HTTPException(status_code=409, detail="no annotated items yet")
    return result


# ── jobs ─────────────────────────────────────────────────────────────────────

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
RUN_FLAGS = {
    "graph": _path_arg, "budget": int, "reps": int, "cascade": bool, "llm_all": bool,
    "no_llm": bool, "replay_only": bool, "flush_every": int, "provider": _word, "model": _word,
    "llm_cache": _path_arg, "runs_file": _path_arg, "template": _path_arg,
    "low_pct": float, "high_pct": float, "low": float, "high": float,
    "results_dir": _path_arg, "save_sequences": _path_arg,
}
ANALYZE_FLAGS = {"k": int, "test_k": int, "ndcg": bool, "no_dedupe": bool}
LABEL_FLAGS = {"graph": _path_arg, "merge": bool}
JOBS = {
    "run": ("benchmark", RUN_FLAGS),
    "analyze": ("benchmark.analyze", ANALYZE_FLAGS),
    "label": ("benchmark.label_graph", LABEL_FLAGS),
}


def build_command(kind: str, args: dict) -> list[str]:
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
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail=f"bad value for {key}: {value!r}")
        cmd += [flag, str(cooked)]
    return cmd


class JobBody(BaseModel):
    kind: str
    args: dict = {}


LAST_JOB_FILE = BENCH_DIR / "analysis" / "last_job.json"


def expected_results(kind: str, args: dict) -> int | None:
    """Result files a run writes: every repeat of every baseline, plus the cascade arm."""
    if kind != "run":
        return None
    from benchmark import POLICIES

    reps = int(args.get("reps", 1))
    return len(POLICIES) * reps + (reps if args.get("cascade") else 0)


class _Job:
    def __init__(self, kind: str, cmd: list[str], args: dict | None = None):
        self.kind, self.cmd = kind, cmd
        self.expected = expected_results(kind, args or {})
        self.started = time.time()
        self.ended: float | None = None
        self.returncode: int | None = None
        self.stopped = False
        self.log: deque[str] = deque(maxlen=LOG_TAIL)
        self.proc: asyncio.subprocess.Process | None = None

    def snapshot(self) -> dict:
        now = self.ended or time.time()
        new = {p.name for d in _result_dirs(self.cmd) for p in d.glob("*.json")
               if p.stat().st_mtime >= self.started}
        text = "\n".join(self.log)
        waits = len(re.findall(r"429|rate.?limit", text, re.I))
        if self.returncode is None:
            state = "running"
        elif self.stopped:
            state = "stopped"
        else:
            state = "done" if self.returncode == 0 else "failed"
        return {"kind": self.kind, "command": " ".join(self.cmd[1:]), "state": state,
                "returncode": self.returncode, "elapsed": round(now - self.started, 1),
                "expected_results": self.expected, "new_results": sorted(new), "rate_limit_mentions": waits, "log": list(self.log)}


def _result_dirs(cmd: list[str]) -> list[Path]:
    if "--results-dir" in cmd:
        return [ROOT / cmd[cmd.index("--results-dir") + 1]]
    return [RESULTS_DIR] if "benchmark" == cmd[2] else []


_job: _Job | None = None


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
        pass


@router.post("/jobs")
async def start_job(body: JobBody):
    global _job
    if _job and _job.returncode is None:
        raise HTTPException(status_code=409, detail="A benchmark job is already running")
    cmd = build_command(body.kind, body.args)
    job = _Job(body.kind, cmd, body.args)
    job.proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=ROOT, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    _job = job
    asyncio.create_task(_pump(job))
    return job.snapshot()


@router.get("/jobs/current")
def current_job():
    if _job:
        return _job.snapshot()
    if LAST_JOB_FILE.is_file():
        try:
            last = json.loads(LAST_JOB_FILE.read_text())
            return {**last, "state": last["state"] if last.get("state") != "running" else "interrupted"}
        except (OSError, ValueError, KeyError):
            pass
    return {"state": "idle", "log": []}


@router.post("/jobs/stop")
async def stop_job():
    if not _job or _job.returncode is not None or _job.proc is None:
        raise HTTPException(status_code=409, detail="No benchmark job is running")
    _job.stopped = True
    _job.proc.terminate()
    return _job.snapshot()
