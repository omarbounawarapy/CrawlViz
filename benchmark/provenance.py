"""What a benchmark result was produced from: code, data, prompts and settings."""
import hashlib
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
        run = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True, check=True,
                                        cwd=Path(__file__).parent).stdout.strip()
        return run("rev-parse", "HEAD") + ("+dirty" if run("status", "--porcelain", "-uno") else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
