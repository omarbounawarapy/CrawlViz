"""The git revision a run was made from, recorded in run manifests."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

GIT_TIMEOUT_SECONDS = 5
DIRTY_MARKER = "+dirty"


def _run_git(repo_dir: Path, *args: str) -> str:
    """Stdout of ``git <args>`` run in ``repo_dir``; raises when git fails."""
    return subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
        check=True,
    ).stdout.strip()


def get_git_revision(repo_dir: Path, *, mark_dirty: bool = False) -> str | None:
    """HEAD of the repository at ``repo_dir``, or None when git cannot say.

    With ``mark_dirty`` a ``+dirty`` suffix flags uncommitted changes to tracked files.
    """
    try:
        revision = _run_git(repo_dir, "rev-parse", "HEAD")
        if mark_dirty and _run_git(repo_dir, "status", "--porcelain", "-uno"):
            revision += DIRTY_MARKER
    except (OSError, subprocess.SubprocessError):
        logger.warning("could not read the git revision of %s", repo_dir, exc_info=True)
        return None
    return revision or None
