import subprocess

from utils import get_git_revision

GIT_IDENTITY = ["-c", "user.name=test", "-c", "user.email=test@example.com"]


def _git(repo, *args):
    subprocess.run(["git", *GIT_IDENTITY, *args], cwd=repo, check=True, capture_output=True)


def _make_repo(path):
    _git(path, "init", "-q")
    (path / "tracked.txt").write_text("one")
    _git(path, "add", "tracked.txt")
    _git(path, "commit", "-q", "-m", "first")


def test_revision_is_the_head_commit(tmp_path):
    _make_repo(tmp_path)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert get_git_revision(tmp_path) == head


def test_dirty_marker_appears_only_when_asked_and_tracked_files_changed(tmp_path):
    _make_repo(tmp_path)
    clean = get_git_revision(tmp_path, mark_dirty=True)
    assert clean is not None and not clean.endswith("+dirty")
    (tmp_path / "tracked.txt").write_text("two")
    assert get_git_revision(tmp_path, mark_dirty=True) == clean + "+dirty"
    assert get_git_revision(tmp_path) == clean


def test_outside_a_repository_the_revision_is_none(tmp_path):
    assert get_git_revision(tmp_path / "missing") is None
