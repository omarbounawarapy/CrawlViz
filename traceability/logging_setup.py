"""The one place logging is configured: JSON lines with the ids that tie a line to a crawl.

Every record becomes a JSON object on one line with ``ts``, ``level``, ``logger`` and
``message``, plus ``crawl_id``, ``node_id`` and ``trace_id`` whenever they are set for the
code that logged. They come from context variables, so a call to ``logger.info`` anywhere
inside a crawl carries them without being passed down:

* ``crawl_id`` is bound by `log_context` for the whole run (``Crawler.start``).
* ``trace_id`` and ``node_id`` are the pair the stages bind per node with
  ``traceability.trace_context.bind_node``.

``CRAWLVIZ_LOG_FORMAT=text`` switches to one readable line per record for development;
``CRAWLVIZ_LOG_LEVEL`` sets the level. Both formats pass the text through
``utils.log_redaction`` first, so a registered secret never reaches a handler.
"""

import json
import logging
import logging.config
import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from utils.log_redaction import redact_secrets

from .trace_context import get_trace, set_trace

LOG_FORMAT_ENV_VAR = "CRAWLVIZ_LOG_FORMAT"
LOG_LEVEL_ENV_VAR = "CRAWLVIZ_LOG_LEVEL"
FORMAT_JSON = "json"
FORMAT_TEXT = "text"
DEFAULT_LOG_FORMAT = FORMAT_JSON
DEFAULT_LOG_LEVEL = "INFO"

# uvicorn installs its own handlers on these; routing them through ours keeps one format.
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")
TEXT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s %(message)s"

_crawl_id: ContextVar[str] = ContextVar("crawl_id", default="")


@contextmanager
def log_context(
    *, crawl_id: str | None = None, trace_id: str | None = None, node_id: str | None = None
) -> Iterator[None]:
    """Stamp the log lines of the enclosed code with these ids, then restore the old ones.

    An id left as None keeps the value already bound. The trace pair belongs to
    ``traceability.trace_context``, which the stages also write; it is restored on exit
    like the crawl id.
    """
    crawl_token = _crawl_id.set(crawl_id) if crawl_id is not None else None
    previous_trace = get_trace()
    binds_trace = trace_id is not None or node_id is not None
    if binds_trace:
        set_trace(
            trace_id if trace_id is not None else previous_trace[0],
            node_id if node_id is not None else previous_trace[1],
        )
    try:
        yield
    finally:
        if binds_trace:
            set_trace(*previous_trace)
        if crawl_token is not None:
            _crawl_id.reset(crawl_token)


def get_log_ids() -> dict[str, str]:
    """The ids bound for the current code, leaving out the ones that are not set."""
    trace_id, node_id = get_trace()
    ids = {"crawl_id": _crawl_id.get(), "node_id": node_id, "trace_id": trace_id}
    return {name: value for name, value in ids.items() if value}


class JsonLineFormatter(logging.Formatter):
    """One JSON object per record: the fixed fields, the bound ids and any exception."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, str] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_secrets(record.getMessage()),
            **get_log_ids(),
        }
        if record.exc_info:
            entry["exception"] = redact_secrets(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False)


class RedactingTextFormatter(logging.Formatter):
    """The readable format, with secrets removed from the whole line."""

    def format(self, record: logging.LogRecord) -> str:
        ids = " ".join(f"{name}={value}" for name, value in get_log_ids().items())
        line = super().format(record)
        return redact_secrets(f"{line} [{ids}]" if ids else line)


def build_logging_config(log_format: str, level: str) -> dict[str, Any]:
    """The ``dictConfig`` for `log_format` (``json`` or ``text``) at `level`."""
    # Any: the dictConfig schema is a plain JSON-shaped mapping.
    formatter: dict[str, Any] = (
        {"()": JsonLineFormatter}
        if log_format == FORMAT_JSON
        else {"()": RedactingTextFormatter, "format": TEXT_FORMAT}
    )
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"crawlviz": formatter},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "crawlviz",
                "stream": "ext://sys.stderr",
            }
        },
        "root": {"level": level, "handlers": ["console"]},
        "loggers": {
            name: {"handlers": ["console"], "level": level, "propagate": False}
            for name in UVICORN_LOGGERS
        },
    }


def configure_logging(log_format: str | None = None, level: str | None = None) -> None:
    """Apply the logging setup; call it once at start. Arguments override the environment.

    Raises:
        ValueError: If the format is not ``json`` or ``text``, or the level is not a level name.
    """
    chosen_format = (log_format or os.environ.get(LOG_FORMAT_ENV_VAR) or DEFAULT_LOG_FORMAT).lower()
    chosen_level = (level or os.environ.get(LOG_LEVEL_ENV_VAR) or DEFAULT_LOG_LEVEL).upper()
    if chosen_format not in (FORMAT_JSON, FORMAT_TEXT):
        raise ValueError(
            f"{LOG_FORMAT_ENV_VAR} must be '{FORMAT_JSON}' or '{FORMAT_TEXT}', "
            f"not {chosen_format!r}."
        )
    if not isinstance(logging.getLevelName(chosen_level), int):
        raise ValueError(
            f"{LOG_LEVEL_ENV_VAR} must be a level name such as INFO, not {chosen_level!r}."
        )
    logging.config.dictConfig(build_logging_config(chosen_format, chosen_level))
