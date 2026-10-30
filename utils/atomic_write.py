"""Write a file so a crash or a full disk never leaves half of it behind."""

import contextlib
import os
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any

TEMP_SUFFIX = ".tmp"


@contextlib.contextmanager
def atomic_open(
    path: str | os.PathLike[str], mode: str = "w", encoding: str | None = "utf-8"
) -> Iterator[IO[Any]]:  # str or bytes handle, chosen by ``mode``
    """Open a temp file beside ``path`` and move it over ``path`` when the block ends.

    The file at ``path`` is replaced only after the new content is flushed to disk;
    if the block raises, the temp file is deleted and ``path`` is left as it was.
    ``mode`` is ``"w"`` for text or ``"wb"`` for bytes.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + TEMP_SUFFIX)
    text_mode = "b" not in mode
    try:
        with open(temp, mode, encoding=encoding if text_mode else None) as handle:
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
