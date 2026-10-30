"""Benchmark job path flags stay inside the directories each flag may read or write."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from routes import benchmark_jobs as jobs

ALLOWED = [
    ("run", {"graph": "benchmark/data/isi.json"}),
    ("run", {"template": "templates/isi.json"}),
    ("run", {"llm_cache": "benchmark/data/exp_cache.jsonl"}),
    ("run", {"runs_file": "benchmark/data/exp_runs.json"}),
    ("run", {"results_dir": "benchmark/results"}),
    ("run", {"results_dir": "benchmark/results/trial_1"}),
    ("run", {"save_sequences": "benchmark/results/sequences.json"}),
    ("label", {"graph": "benchmark/data/isi.json"}),
]

REFUSED = [
    # Outputs that would overwrite code, settings or secrets inside the project.
    ("run", {"llm_cache": "benchmark/policies.py"}),
    ("run", {"runs_file": "main.py"}),
    ("run", {"runs_file": "keys.json"}),
    ("run", {"save_sequences": "benchmark/runner.py"}),
    ("run", {"save_sequences": "config/config.py"}),
    ("run", {"results_dir": "benchmark"}),
    ("run", {"results_dir": "core"}),
    ("run", {"results_dir": "templates"}),
    # Inputs outside the folder they come from.
    ("run", {"graph": "keys.json"}),
    ("run", {"graph": "benchmark/results/x.json"}),
    ("run", {"template": "benchmark/data/isi.json"}),
    ("label", {"graph": "main.py"}),
    # Not plain relative paths at all.
    ("run", {"graph": "/etc/passwd"}),
    ("run", {"graph": "benchmark/data/../../keys.json"}),
    ("run", {"results_dir": "-rf"}),
    ("run", {"results_dir": "benchmark/results/../../core"}),
]


@pytest.mark.parametrize(("kind", "args"), ALLOWED)
def test_paths_inside_their_directory_reach_the_command(kind: str, args: dict[str, str]) -> None:
    ((flag, value),) = args.items()
    command = jobs.build_command(kind, args)
    assert command[command.index("--" + flag.replace("_", "-")) + 1] == value


@pytest.mark.parametrize(("kind", "args"), REFUSED)
def test_paths_outside_their_directory_are_refused(kind: str, args: dict[str, str]) -> None:
    with pytest.raises(HTTPException) as refused:
        jobs.build_command(kind, args)
    assert refused.value.status_code == 422


def test_a_symlink_out_of_the_output_directory_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    results = tmp_path / "root" / "benchmark" / "results"
    results.mkdir(parents=True)
    (results / "escape").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(jobs, "ROOT", tmp_path / "root")
    monkeypatch.setattr(jobs, "RESULTS_DIR", results)
    monkeypatch.setattr(jobs, "DATA_DIR", tmp_path / "root" / "benchmark" / "data")
    with pytest.raises(HTTPException):
        jobs.build_command("run", {"results_dir": "benchmark/results/escape"})
