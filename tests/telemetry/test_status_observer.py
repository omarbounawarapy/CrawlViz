"""The status observer: first change at once, later ones coalesced per subsystem."""

import asyncio
import logging
import threading
from collections.abc import AsyncIterator

import pytest

from crawlviz.contracts import LlmFacts, LlmStatus, SubsystemStatus
from crawlviz.telemetry import STATUS_COALESCE_MS, StatusBoard, StatusObserver

WINDOW_MS = 100
WINDOW_SECONDS = WINDOW_MS / 1000
# Longer than a window plus the scheduling jitter of a loaded test machine.
PAST_THE_WINDOW = WINDOW_SECONDS * 3


class Sent:
    """What the observer sent, in order."""

    def __init__(self) -> None:
        self.entries: list[SubsystemStatus] = []

    async def __call__(self, entry: SubsystemStatus) -> None:
        self.entries.append(entry)

    def calls_sent(self, subsystem: str) -> list[int]:
        return [
            entry.facts.calls
            for entry in self.entries
            if isinstance(entry, LlmStatus) and entry.subsystem == subsystem
        ]


@pytest.fixture
def board() -> StatusBoard:
    return StatusBoard()


@pytest.fixture
def sent() -> Sent:
    return Sent()


@pytest.fixture
async def observer(board: StatusBoard, sent: Sent) -> AsyncIterator[StatusObserver]:
    observer = StatusObserver(board, sent, coalesce_ms=WINDOW_MS)
    observer.start()
    yield observer
    await observer.stop()


def test_the_window_is_a_quarter_of_a_second() -> None:
    assert STATUS_COALESCE_MS == 250


@pytest.mark.asyncio
async def test_the_first_change_is_sent_at_once(
    observer: StatusObserver, board: StatusBoard, sent: Sent
) -> None:
    board.report("embedder", "starting", "loading_model")
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert [(e.subsystem, e.state) for e in sent.entries] == [("embedder", "starting")]


@pytest.mark.asyncio
async def test_changes_inside_the_window_are_sent_once_as_the_newest(
    observer: StatusObserver, board: StatusBoard, sent: Sent
) -> None:
    board.report("llm", "ready", None, LlmFacts(calls=1))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    for calls in range(2, 21):
        board.report("llm", "ready", None, LlmFacts(calls=calls))
        await asyncio.sleep(0)
    await asyncio.sleep(PAST_THE_WINDOW)

    assert sent.calls_sent("llm") == [1, 20]


@pytest.mark.asyncio
async def test_a_change_after_the_window_is_sent_at_once(
    observer: StatusObserver, board: StatusBoard, sent: Sent
) -> None:
    board.report("llm", "ready", None, LlmFacts(calls=1))
    await asyncio.sleep(PAST_THE_WINDOW)

    board.report("llm", "ready", None, LlmFacts(calls=2))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert sent.calls_sent("llm") == [1, 2]


@pytest.mark.asyncio
async def test_a_busy_subsystem_does_not_hold_back_another(
    observer: StatusObserver, board: StatusBoard, sent: Sent
) -> None:
    board.report("llm", "ready", None, LlmFacts(calls=1))
    board.report("llm", "ready", None, LlmFacts(calls=2))
    board.report("fetch", "ready")
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert [e.subsystem for e in sent.entries] == ["llm", "fetch"]


@pytest.mark.asyncio
async def test_a_change_that_returns_to_what_was_sent_is_not_sent_again(
    observer: StatusObserver, board: StatusBoard, sent: Sent
) -> None:
    board.report("llm", "ready", None, LlmFacts(calls=1))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    board.report("llm", "ready", None, LlmFacts(calls=2))
    board.report("llm", "ready", None, LlmFacts(calls=1))
    await asyncio.sleep(PAST_THE_WINDOW)

    assert sent.calls_sent("llm") == [1]


@pytest.mark.asyncio
async def test_a_report_from_another_thread_is_sent_on_the_loop(
    observer: StatusObserver, board: StatusBoard, sent: Sent
) -> None:
    loop_thread = threading.get_ident()
    sender_threads: list[int] = []
    original = observer._send

    async def record_thread(entry: SubsystemStatus) -> None:
        sender_threads.append(threading.get_ident())
        await original(entry)

    observer._send = record_thread
    reporter = threading.Thread(target=board.report, args=("embedder", "ready"))

    reporter.start()
    await asyncio.to_thread(reporter.join)
    await asyncio.sleep(PAST_THE_WINDOW)

    assert [e.subsystem for e in sent.entries] == ["embedder"]
    assert sender_threads == [loop_thread]


@pytest.mark.asyncio
async def test_stopping_sends_the_change_that_was_being_held(
    board: StatusBoard, sent: Sent
) -> None:
    observer = StatusObserver(board, sent, coalesce_ms=WINDOW_MS)
    observer.start()
    board.report("llm", "ready", None, LlmFacts(calls=1))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    board.report("llm", "ready", None, LlmFacts(calls=2))
    await asyncio.sleep(0)

    await observer.stop()

    assert sent.calls_sent("llm") == [1, 2]


@pytest.mark.asyncio
async def test_nothing_is_sent_after_stopping(board: StatusBoard, sent: Sent) -> None:
    observer = StatusObserver(board, sent, coalesce_ms=WINDOW_MS)
    observer.start()
    await observer.stop()

    board.report("fetch", "ready")
    await asyncio.sleep(PAST_THE_WINDOW)

    assert sent.entries == []


@pytest.mark.asyncio
async def test_a_failing_send_is_logged_and_the_next_change_is_still_sent(
    board: StatusBoard, caplog: pytest.LogCaptureFixture
) -> None:
    attempts: list[int] = []

    async def fail_first(entry: SubsystemStatus) -> None:
        attempts.append(len(attempts))
        if len(attempts) == 1:
            raise ConnectionError("gateway closed")

    observer = StatusObserver(board, fail_first, coalesce_ms=WINDOW_MS)
    observer.start()

    with caplog.at_level(logging.ERROR, logger="crawlviz.telemetry.status_observer"):
        board.report("fetch", "ready")
        await asyncio.sleep(PAST_THE_WINDOW)
        board.report("fetch", "waiting", "backing_off")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    await observer.stop()

    assert len(attempts) == 2
    assert "Sending the fetch status failed" in caplog.text


@pytest.mark.asyncio
async def test_reports_in_one_turn_of_the_loop_are_sent_as_the_newest(
    observer: StatusObserver, board: StatusBoard, sent: Sent
) -> None:
    for calls in range(1, 11):
        board.report("llm", "ready", None, LlmFacts(calls=calls))
    await asyncio.sleep(PAST_THE_WINDOW)

    assert sent.calls_sent("llm") == [10]
