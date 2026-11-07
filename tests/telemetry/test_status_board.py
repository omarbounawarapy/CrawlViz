"""The status board: what counts as a change, what a bad report does, and use from threads."""

import logging
import threading

import pytest
from pydantic import ValidationError

from crawlviz.contracts import (
    SUBSYSTEMS,
    EmbedderFacts,
    EmbedderStatus,
    LlmFacts,
    LlmStatus,
    SubsystemStatus,
)
from crawlviz.events import StatusReporter
from crawlviz.telemetry import StatusBoard


class Clock:
    """A clock the test moves by hand."""

    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def board(clock: Clock) -> StatusBoard:
    return StatusBoard(clock=clock)


@pytest.fixture
def heard(board: StatusBoard) -> list[SubsystemStatus]:
    entries: list[SubsystemStatus] = []
    board.add_listener(entries.append)
    return entries


def test_the_board_starts_with_every_subsystem_off(board: StatusBoard) -> None:
    entries = board.snapshot().subsystems

    assert tuple(entries) == SUBSYSTEMS
    assert {entry.state for entry in entries.values()} == {"off"}
    assert {entry.since for entry in entries.values()} == {1_000.0}


def test_the_board_is_a_status_reporter(board: StatusBoard) -> None:
    reporter: StatusReporter = board

    reporter.report("embedder", "starting", "loading_model")

    assert board.snapshot().subsystems["embedder"].state == "starting"


def test_a_report_replaces_the_entry_and_stamps_the_time(board: StatusBoard, clock: Clock) -> None:
    clock.now = 1_005.0

    board.report("embedder", "starting", "loading_model")

    entry = board.snapshot().subsystems["embedder"]
    assert isinstance(entry, EmbedderStatus)
    assert (entry.state, entry.reason, entry.since) == ("starting", "loading_model", 1_005.0)


def test_a_report_for_one_subsystem_leaves_the_others_alone(board: StatusBoard) -> None:
    before = board.snapshot()

    board.report("fetch", "ready")

    after = board.snapshot()
    assert after.subsystems["fetch"].state == "ready"
    assert {name: entry for name, entry in after.subsystems.items() if name != "fetch"} == {
        name: entry for name, entry in before.subsystems.items() if name != "fetch"
    }


def test_a_snapshot_taken_earlier_does_not_change(board: StatusBoard) -> None:
    before = board.snapshot()

    board.report("fetch", "ready")

    assert before.subsystems["fetch"].state == "off"


def test_listeners_hear_a_change(board: StatusBoard, heard: list[SubsystemStatus]) -> None:
    board.report("embedder", "starting", "loading_model")

    assert [(entry.subsystem, entry.state) for entry in heard] == [("embedder", "starting")]


def test_a_repeated_report_changes_nothing_and_is_not_announced(
    board: StatusBoard, clock: Clock, heard: list[SubsystemStatus]
) -> None:
    board.report("embedder", "starting", "loading_model")
    first = board.snapshot()
    clock.now += 30.0

    board.report("embedder", "starting", "loading_model")

    assert board.snapshot() is first
    assert len(heard) == 1


def test_new_facts_are_a_change_and_keep_the_time_the_state_began(
    board: StatusBoard, clock: Clock, heard: list[SubsystemStatus]
) -> None:
    board.report("llm", "ready", None, LlmFacts(calls=1))
    clock.now += 30.0

    board.report("llm", "ready", None, LlmFacts(calls=2))

    entry = board.snapshot().subsystems["llm"]
    assert isinstance(entry, LlmStatus)
    assert (entry.facts.calls, entry.since) == (2, 1_000.0)
    assert len(heard) == 2


def test_a_new_state_restarts_the_time_in_state(board: StatusBoard, clock: Clock) -> None:
    board.report("llm", "ready")
    clock.now += 30.0

    board.report("llm", "waiting", "rate_limited", retry_at=1_100.0)

    entry = board.snapshot().subsystems["llm"]
    assert (entry.state, entry.since, entry.retry_at) == ("waiting", 1_030.0, 1_100.0)


@pytest.mark.parametrize(
    ("subsystem", "state", "reason"),
    [
        ("embedder", "failed", "rate_limited"),
        ("llm", "waiting", None),
        ("fetch", "ready", "not_a_reason"),
    ],
)
def test_an_invalid_report_raises_and_leaves_the_board_as_it_was(
    board: StatusBoard,
    heard: list[SubsystemStatus],
    subsystem: str,
    state: str,
    reason: str | None,
) -> None:
    before = board.snapshot()

    with pytest.raises(ValidationError):
        board.report(subsystem, state, reason)  # type: ignore[arg-type]

    assert board.snapshot() is before
    assert heard == []


def test_facts_of_another_subsystem_are_refused(board: StatusBoard) -> None:
    with pytest.raises(ValidationError):
        board.report("embedder", "ready", None, LlmFacts())


def test_a_removed_listener_hears_nothing(board: StatusBoard, heard: list[SubsystemStatus]) -> None:
    board.remove_listener(heard.append)

    board.report("fetch", "ready")

    assert heard == []


def test_a_failing_listener_is_logged_and_does_not_stop_the_report(
    board: StatusBoard, heard: list[SubsystemStatus], caplog: pytest.LogCaptureFixture
) -> None:
    def fail(entry: SubsystemStatus) -> None:
        raise RuntimeError("listener bug")

    board.add_listener(fail)

    with caplog.at_level(logging.ERROR, logger="crawlviz.telemetry.status_board"):
        board.report("fetch", "ready")

    assert board.snapshot().subsystems["fetch"].state == "ready"
    assert len(heard) == 1
    assert "fetch subsystem" in caplog.text


def test_reports_from_many_threads_are_all_applied_and_each_change_is_announced_once() -> None:
    board = StatusBoard()
    heard: list[SubsystemStatus] = []
    board.add_listener(heard.append)
    threads_count, reports_each = 8, 50
    start = threading.Barrier(threads_count)

    def report_many(offset: int) -> None:
        start.wait()
        for step in range(reports_each):
            calls = offset * reports_each + step + 1
            board.report("llm", "ready", None, LlmFacts(calls=calls))

    threads = [threading.Thread(target=report_many, args=(n,)) for n in range(threads_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # Every report carries distinct facts, so every one is a change and none is lost.
    announced = [entry.facts.calls for entry in heard if isinstance(entry, LlmStatus)]
    assert sorted(announced) == list(range(1, threads_count * reports_each + 1))
    final = board.snapshot().subsystems["llm"]
    assert isinstance(final, LlmStatus)
    assert final.facts.calls in announced


def test_threads_reporting_the_same_state_announce_it_once() -> None:
    board = StatusBoard()
    heard: list[SubsystemStatus] = []
    board.add_listener(heard.append)
    threads_count = 16
    start = threading.Barrier(threads_count)

    def report_same() -> None:
        start.wait()
        board.report("embedder", "ready", None, EmbedderFacts(model="m", device="cpu"))

    threads = [threading.Thread(target=report_same) for _ in range(threads_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(heard) == 1
