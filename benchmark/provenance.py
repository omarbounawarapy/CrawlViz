"""What a benchmark result was produced from: code, data, prompts and settings."""
import hashlib
import json
import subprocess
from pathlib import Path

RUBRIC = Path(__file__).with_name("rubric.md")
PROMPTS = Path(__file__).resolve().parent.parent / "models" / "prompts.py"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prompt_version(strategy: str) -> str:
    """The scoring strategy and a hash of the prompt templates it draws from."""
    return f"{strategy}:{file_sha256(PROMPTS)[:12]}"


def git_commit() -> str:
    """HEAD, with ``+dirty`` when tracked files have uncommitted changes."""
    try:
        def run(*args: str) -> str:
            return subprocess.run(["git", *args], capture_output=True, text=True, check=True,
                                  cwd=Path(__file__).parent).stdout.strip()

        return run("rev-parse", "HEAD") + ("+dirty" if run("status", "--porcelain", "-uno") else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def graph_sha256(graph_path: Path | None, graph=None) -> str:
    """The graph file's hash; for a generated graph, the hash of its pages."""
    if graph_path:
        return file_sha256(graph_path)
    return hashlib.sha256(json.dumps(graph.pages, sort_keys=True).encode()).hexdigest()


def rubric_sha256(graph_path: Path | None) -> str | None:
    """The hash of the rubric the graph was labelled under, as recorded in it."""
    if not graph_path:
        return None
    return json.loads(Path(graph_path).read_text()).get("rubric_sha256")


def manifest(
    graph_path: Path | None, graph, result, *, budget: int, seed: int, rep: int,
    model: str | None = None, provider: str | None = None, prompt: str | None = None,
) -> dict:
    """Everything needed to say what produced a result and to reproduce it."""
    return {
        "git_commit": git_commit(),
        "graph_sha256": graph_sha256(graph_path, graph),
        "rubric_sha256": rubric_sha256(graph_path),
        "model": model,
        "provider": provider,
        "prompt_version": prompt,
        "budget": budget,
        "thresholds": result.thresholds,
        "seed": seed,
        "repeat": rep,
        "absent_page_mode": graph_module().ABSENT_PAGE_HITS,
    }


def graph_module():
    from . import graph

    return graph
