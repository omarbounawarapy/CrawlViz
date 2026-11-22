"""Write a file so a crash or a full disk never leaves half of it behind."""

import contextlib
import os
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any

TEMP_SUFFIX = ".tmp"
# Create the temp file or fail: never open one that exists, and never follow a symlink.
NEW_FILE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
# What ``open(path, "w")`` uses, so the process umask still decides the mode by default.
DEFAULT_FILE_MODE = 0o666


@contextlib.contextmanager
def atomic_open(
    path: str | os.PathLike[str],
    mode: str = "w",
    encoding: str | None = "utf-8",
    *,
    file_mode: int | None = None,
) -> Iterator[IO[Any]]:  # str or bytes handle, chosen by ``mode``
    """Open a temp file beside ``path`` and move it over ``path`` when the block ends.

    The file at ``path`` is replaced only after the new content is flushed to disk;
    if the block raises, the temp file is deleted and ``path`` is left as it was.
    ``mode`` is ``"w"`` for text or ``"wb"`` for bytes.

    A temp file left by an earlier run is deleted first, never reused: another user may
    hold it open or have put a symlink there. The new temp file is created in one step
    and fails if anything is already at that path, so it is never written through a
    symlink. ``file_mode`` sets its permissions at creation (for example ``0o600`` for a
    secrets file), so it is never readable more widely, not even for a moment; the
    default is the process umask applied to ``0o666``, like ``open``.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + TEMP_SUFFIX)
    text_mode = "b" not in mode
    create_mode = DEFAULT_FILE_MODE if file_mode is None else file_mode
    try:
        temp.unlink(missing_ok=True)
        fd = os.open(temp, NEW_FILE_FLAGS, create_mode)
        with os.fdopen(fd, mode, encoding=encoding if text_mode else None) as handle:
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def write_text_atomic(path: str | os.PathLike[str], text: str) -> None:
    """Replace the file at ``path`` with ``text``."""
    with atomic_open(path) as handle:
        handle.write(text)
