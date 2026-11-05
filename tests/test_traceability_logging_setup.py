"""Log records are JSON lines carrying crawl_id, node_id and trace_id (OBS-1)."""

import asyncio
import json
import logging
from collections.abc import Iterator

import pytest

from traceability.logging_setup import (
    FORMAT_TEXT,
    LOG_FORMAT_ENV_VAR,
    configure_logging,
    get_log_ids,
    log_context,
)
from traceability.trace_context import bind_node, get_trace
from utils.log_redaction import REDACTED, clear_registered_secrets, register_secrets

API_KEY = "gsk_ThisIsAFakeKeyForTests1234567890"


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    clear_registered_secrets()


def emitted_lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return [line for line in capsys.readouterr().err.splitlines() if line]


def test_a_record_is_one_json_line_with_the_fixed_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json", "INFO")
    logging.getLogger("crawlviz.sample").info("fetched %d pages", 3)
    (line,) = emitted_lines(capsys)
    entry = json.loads(line)
    assert entry["level"] == "INFO"
    assert entry["logger"] == "crawlviz.sample"
    assert entry["message"] == "fetched 3 pages"
    assert entry["ts"].endswith("+00:00")
    assert "crawl_id" not in entry


def test_the_bound_ids_are_added_while_the_context_is_open(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json", "INFO")
    log = logging.getLogger("crawlviz.sample")
    with log_context(crawl_id="wiki-2026", trace_id="t-1", node_id="n-9"):
        log.info("inside")
    log.info("outside")
    inside, outside = (json.loads(line) for line in emitted_lines(capsys))
    assert (inside["crawl_id"], inside["trace_id"], inside["node_id"]) == (
        "wiki-2026",
        "t-1",
        "n-9",
    )
    assert not {"crawl_id", "trace_id", "node_id"} & outside.keys()
    assert get_trace() == ("", "")


def test_a_node_bound_by_a_stage_is_logged_with_the_crawl_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json", "INFO")
    log = logging.getLogger("crawlviz.sample")

    async def stage() -> str:
        trace_id = bind_node("node-42")
        log.info("scoring")
        return trace_id

    async def crawl() -> str:
        with log_context(crawl_id="run-1"):
            # A stage runs as its own task, which inherits the crawl id.
            return await asyncio.create_task(stage())

    trace_id = asyncio.run(crawl())
    entry = json.loads(emitted_lines(capsys)[0])
    assert entry["crawl_id"] == "run-1"
    assert entry["node_id"] == "node-42"
    assert entry["trace_id"] == trace_id


def test_nested_contexts_restore_the_outer_ids() -> None:
    with log_context(crawl_id="outer"):
        with log_context(crawl_id="inner"):
            assert get_log_ids() == {"crawl_id": "inner"}
        assert get_log_ids() == {"crawl_id": "outer"}
    assert get_log_ids() == {}


def test_the_context_is_restored_when_the_body_raises() -> None:
    with pytest.raises(RuntimeError), log_context(crawl_id="run-1", trace_id="t", node_id="n"):
        raise RuntimeError("boom")
    assert get_log_ids() == {}


def test_an_exception_is_logged_in_the_exception_field(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json", "INFO")
    try:
        raise ValueError("bad page")
    except ValueError:
        logging.getLogger("crawlviz.sample").exception("crawl failed")
    entry = json.loads(emitted_lines(capsys)[0])
    assert entry["message"] == "crawl failed"
    assert "ValueError: bad page" in entry["exception"]


def test_a_registered_api_key_is_redacted_in_the_message_and_the_exception(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json", "INFO")
    register_secrets([API_KEY])
    try:
        raise RuntimeError(f"provider refused {API_KEY}")
    except RuntimeError:
        logging.getLogger("crawlviz.sample").exception("call used %s", API_KEY)
    output = capsys.readouterr().err
    assert API_KEY not in output
    assert REDACTED in json.loads(output)["message"]


def test_text_format_is_readable_and_also_redacts(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(FORMAT_TEXT, "INFO")
    register_secrets([API_KEY])
    with log_context(crawl_id="run-1"):
        logging.getLogger("crawlviz.sample").warning("using %s", API_KEY)
    (line,) = emitted_lines(capsys)
    assert line.endswith(f"crawlviz.sample using {REDACTED} [crawl_id=run-1]")
    assert API_KEY not in line


def test_the_format_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(LOG_FORMAT_ENV_VAR, FORMAT_TEXT)
    configure_logging()
    logging.getLogger("crawlviz.sample").info("plain")
    (line,) = emitted_lines(capsys)
    assert not line.startswith("{")


def test_the_level_filters_records(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("json", "WARNING")
    logging.getLogger("crawlviz.sample").info("quiet")
    assert emitted_lines(capsys) == []


@pytest.mark.parametrize(("log_format", "level"), [("xml", "INFO"), ("json", "LOUD")])
def test_an_unknown_format_or_level_is_refused_with_a_message(log_format: str, level: str) -> None:
    with pytest.raises(ValueError, match="must be"):
        configure_logging(log_format, level)


def test_uvicorn_loggers_use_the_same_format(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("json", "INFO")
    logging.getLogger("uvicorn.error").info("Application startup complete.")
    entry = json.loads(emitted_lines(capsys)[0])
    assert entry["logger"] == "uvicorn.error"
