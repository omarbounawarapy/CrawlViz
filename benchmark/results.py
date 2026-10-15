"""One JSON file per policy run, so analysis never parses console output.

A file holds what identifies the run (graph, policy, repeat, budget), what it
did (page sequence and the label of each page), whether it counts (``valid``),
and what it cost (LLM calls, tokens, timings). ``benchmark.analyze`` reads
these files.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .runner import RunResult

FORMAT = 1


@dataclass
class RunRecord:
    graph: str
    policy: str
    rep: int
    budget: int
    sequence: list[str]
    labels: list[int]
    valid: bool
    status: str
    problems: list[str] = field(default_factory=list)
    llm_calls: int = 0  # live calls
    llm_replayed: int = 0  # answers served from the cache
    input_tokens: int = 0
    output_tokens: int = 0
    wall_seconds: float = 0.0
    llm_seconds: float = 0.0  # sum of live call latencies
    wait_seconds: float = 0.0  # pacing and rate-limit sleeps
    rate_limit_waits: int = 0
    rate_limit_seconds: float = 0.0  # 429 back-off sleeps, part of wait_seconds
    absent_page_hits: int = 0  # requests for pages outside the frozen graph
    replay: bool = False  # produced with --replay-only
    replay_misses: int = 0  # LLM lookups a replay could not find in the cache
    scoring_failures: int = 0
    empty_results: int = 0
    settings: dict = field(default_factory=dict)  # flush_every, thresholds, ...
    manifest: dict = field(default_factory=dict)  # provenance, see benchmark.provenance.manifest

    @classmethod
    def from_result(cls, graph: str, rep: int, budget: int, result: RunResult, **extra) -> "RunRecord":
        h = result.health
        return cls(
            graph=graph, policy=result.policy, rep=rep, budget=budget,
            sequence=list(result.visited), labels=[int(v) for v in result.labels],
            valid=h.valid, status=h.status, problems=list(h.problems),
            wall_seconds=round(result.wall_seconds, 3),
            absent_page_hits=result.absent_page_hits,
            scoring_failures=h.scoring_failures, empty_results=h.empty_results,
            **extra,
        )

    def to_json(self) -> dict:
        return {"format": FORMAT, **self.__dict__}

    @classmethod
    def from_json(cls, data: dict) -> "RunRecord":
        data = {k: v for k, v in data.items() if k != "format"}
        return cls(**data)

    def filename(self) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{self.graph}__{self.policy}__rep{self.rep}")
        return safe + ".json"


class ResultSink:
    """Writes each record as it arrives and keeps the page sequences."""

    def __init__(self, directory: Path | None, sequences_file: Path | None = None):
        self.directory = Path(directory) if directory else None
        self.sequences_file = Path(sequences_file) if sequences_file else None
        self.sequences: dict[str, list[str]] = {}

    def add(self, record: RunRecord) -> None:
        self.sequences[f"{record.graph}:{record.policy}:rep{record.rep}"] = record.sequence
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=True)
            name = record.filename()
            if record.replay:  # a replay never overwrites the live run it reproduces
                name = name.replace(".json", "__replay-miss.json" if record.replay_misses else "__replay.json")
            (self.directory / name).write_text(
                json.dumps(record.to_json(), ensure_ascii=False, indent=1)
            )
        if self.sequences_file:
            self.sequences_file.parent.mkdir(parents=True, exist_ok=True)
            self.sequences_file.write_text(json.dumps(self.sequences, ensure_ascii=False))


def load_records(directory: Path) -> list[RunRecord]:
    return [
        RunRecord.from_json(json.loads(p.read_text()))
        for p in sorted(Path(directory).glob("*.json"))
    ]
