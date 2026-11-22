"""The state of each subsystem a crawl depends on, and how one report changes it (ADR 8).

A status board holds one entry per subsystem. The subsystems are one fixed list: the
members of ``SubsystemStatus``. Adding a subsystem is one entry model, with its reasons and
facts, added to that union and to ``SubsystemName`` (ARCH-6).

Each entry carries:

* ``state``: ``off``, ``starting``, ``ready``, ``waiting`` or ``failed``.
* ``reason``: a snake_case code from the subsystem's own closed list, never a sentence. The
  UI turns ``llm`` / ``waiting`` / ``rate_limited`` into words (ADR 8, decision 6).
  ``waiting`` and ``failed`` always name a reason, so the UI can say what happened.
* ``since``: when the subsystem entered this state and reason (unix seconds).
* ``retry_at``: when a ``waiting`` subsystem tries again (unix seconds), if it knows.
* ``facts``: typed per subsystem, for example the embedder's model and device.

``apply_report`` is the pure reducer the board holder calls for each report. It returns the
snapshot it was given when the report changes nothing, so the holder can tell a change from
a repeat without comparing entries itself. Building and applying a report is O(1) in the
size of the crawl, so a producer can report from a hot path (PERF-3).
"""

from __future__ import annotations

from typing import Annotated, Final, Literal, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    StringConstraints,
    TypeAdapter,
    model_validator,
)

SubsystemName = Literal["embedder", "space", "llm", "fetch", "robots", "export"]
SubsystemState = Literal["off", "starting", "ready", "waiting", "failed"]

# States that leave the user waiting or stuck: the UI must be able to say why.
STATES_THAT_NEED_A_REASON: Final[frozenset[SubsystemState]] = frozenset({"waiting", "failed"})

# A code the UI looks up in its catalog: lowercase snake_case, bounded in length.
SnakeCaseCode = Annotated[
    str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$", max_length=64)
]


class _Contract(BaseModel):
    """Status models reject unknown keys and never change after they are built."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Facts, one model per subsystem -------------------------------------------------------


class EmbedderFacts(_Contract):
    """The embedding model in use. ``model`` names the offline hashing double when offline."""

    model: str | None = None
    device: str | None = None
    dimensions: int | None = Field(default=None, ge=1)


class SpaceFacts(_Contract):
    """The topic's semantic space: how many vectors it holds and whether it was a saved one."""

    vectors: NonNegativeInt | None = None
    loaded_from_store: bool | None = None


class LlmFacts(_Contract):
    """LLM use so far in this crawl.

    The counters keep the names of ``LlmCallTotals`` (``crawlviz.llm``), so one key means
    the same thing in the call records, the board and the UI (NAME-5). ``budget_calls`` is
    null when calls are not capped, and ``estimated_cost_usd`` while no call has a known
    price. ``outcomes`` counts calls by how they ended, keyed by the outcome code.
    """

    provider: str | None = None
    model: str | None = None
    calls: NonNegativeInt = 0
    budget_calls: NonNegativeInt | None = None
    calls_refused: NonNegativeInt = 0
    cache_hits: NonNegativeInt = 0
    failed_calls: NonNegativeInt = 0
    input_tokens: NonNegativeInt = 0
    output_tokens: NonNegativeInt = 0
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    in_flight: NonNegativeInt = 0
    outcomes: dict[SnakeCaseCode, NonNegativeInt] = Field(default_factory=dict)


class FetchFacts(_Contract):
    """Page requests: in flight, done, hosts the crawl is backing off from, retries queued."""

    in_flight: NonNegativeInt = 0
    pages_fetched: NonNegativeInt = 0
    hosts_backing_off: NonNegativeInt = 0
    retries_pending: NonNegativeInt = 0


class RobotsFacts(_Contract):
    """robots.txt: hosts whose rules are known, hosts refused because the rules failed to
    load (a 5xx fails closed), and the longest Crawl-delay in force."""

    hosts_checked: NonNegativeInt = 0
    hosts_blocked: NonNegativeInt = 0
    crawl_delay_s: float | None = Field(default=None, ge=0)


class ExportFacts(_Contract):
    """Rows written to the export so far, and rows that could not be written."""

    rows_written: NonNegativeInt = 0
    rows_failed: NonNegativeInt = 0


# --- Reasons, one closed list per subsystem -----------------------------------------------

EmbedderReason = Literal["loading_model", "model_missing", "load_failed"]
SpaceReason = Literal["waiting_for_embedder", "loading_saved", "building", "build_failed"]
LlmReason = Literal["keys_missing", "rate_limited", "budget_exhausted", "provider_error"]
FetchReason = Literal["rate_limited", "backing_off", "network_errors"]
RobotsReason = Literal["loading_rules", "rules_unavailable"]
ExportReason = Literal["write_failed"]


# --- Entries ------------------------------------------------------------------------------


class _Entry(_Contract):
    state: SubsystemState
    since: float = Field(ge=0)
    retry_at: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _reason_and_retry_fit_the_state(self) -> _Entry:
        reason: str | None = getattr(self, "reason", None)
        if self.state in STATES_THAT_NEED_A_REASON and reason is None:
            raise ValueError(f"a '{self.state}' status needs a reason code")
        if self.retry_at is not None and self.state != "waiting":
            raise ValueError(f"retry_at is only for a 'waiting' status, not '{self.state}'")
        return self


class EmbedderStatus(_Entry):
    subsystem: Literal["embedder"] = "embedder"
    reason: EmbedderReason | None = None
    facts: EmbedderFacts = Field(default_factory=EmbedderFacts)


class SpaceStatus(_Entry):
    subsystem: Literal["space"] = "space"
    reason: SpaceReason | None = None
    facts: SpaceFacts = Field(default_factory=SpaceFacts)


class LlmStatus(_Entry):
    subsystem: Literal["llm"] = "llm"
    reason: LlmReason | None = None
    facts: LlmFacts = Field(default_factory=LlmFacts)


class FetchStatus(_Entry):
    subsystem: Literal["fetch"] = "fetch"
    reason: FetchReason | None = None
    facts: FetchFacts = Field(default_factory=FetchFacts)


class RobotsStatus(_Entry):
    subsystem: Literal["robots"] = "robots"
    reason: RobotsReason | None = None
    facts: RobotsFacts = Field(default_factory=RobotsFacts)


class ExportStatus(_Entry):
    subsystem: Literal["export"] = "export"
    reason: ExportReason | None = None
    facts: ExportFacts = Field(default_factory=ExportFacts)


SubsystemStatus = Annotated[
    EmbedderStatus | SpaceStatus | LlmStatus | FetchStatus | RobotsStatus | ExportStatus,
    Field(discriminator="subsystem"),
]
SubsystemFacts = EmbedderFacts | SpaceFacts | LlmFacts | FetchFacts | RobotsFacts | ExportFacts

# The board's order, which is also the order the UI shows the subsystems in.
SUBSYSTEMS: Final[tuple[SubsystemName, ...]] = get_args(SubsystemName)

_STATUS_ADAPTER: Final[TypeAdapter[SubsystemStatus]] = TypeAdapter(SubsystemStatus)


class StatusBoardSnapshot(_Contract):
    """Every subsystem's entry at one moment, keyed and ordered by ``SUBSYSTEMS``."""

    subsystems: dict[SubsystemName, SubsystemStatus]

    @model_validator(mode="after")
    def _one_entry_per_subsystem(self) -> StatusBoardSnapshot:
        if tuple(self.subsystems) != SUBSYSTEMS:
            raise ValueError(
                f"the board needs one entry for each of {list(SUBSYSTEMS)}, in that order; "
                f"it has {list(self.subsystems)}"
            )
        for name, entry in self.subsystems.items():
            if entry.subsystem != name:
                raise ValueError(f"the entry under '{name}' is for '{entry.subsystem}'")
        return self


def make_report(  # noqa: PLR0913 (one parameter per field of the entry)
    subsystem: SubsystemName,
    state: SubsystemState,
    reason: str | None,
    facts: SubsystemFacts | None,
    now: float,
    retry_at: float | None = None,
) -> SubsystemStatus:
    """One validated entry from the arguments of ``StatusReporter.report``.

    Raises ``pydantic.ValidationError`` when the reason is not in the subsystem's list, the
    facts belong to another subsystem, or the state needs a reason that is missing.
    """
    fields: dict[str, object] = {
        "subsystem": subsystem,
        "state": state,
        "reason": reason,
        "since": now,
        "retry_at": retry_at,
    }
    if facts is not None:
        fields["facts"] = facts
    return _STATUS_ADAPTER.validate_python(fields)


def initial_board(now: float) -> StatusBoardSnapshot:
    """The board before anything has reported: every subsystem ``off`` since ``now``."""
    return StatusBoardSnapshot(
        subsystems={name: make_report(name, "off", None, None, now) for name in SUBSYSTEMS}
    )


def apply_report(board: StatusBoardSnapshot, report: SubsystemStatus) -> StatusBoardSnapshot:
    """The board with ``report`` as its subsystem's entry.

    ``since`` is kept from the current entry while the state and reason stay the same, so it
    says how long the subsystem has been in this state. When nothing changes at all, the
    same ``board`` object is returned.
    """
    current = board.subsystems[report.subsystem]
    if (current.state, current.reason) == (report.state, report.reason):
        report = report.model_copy(update={"since": current.since})
    if report == current:
        return board
    return board.model_copy(update={"subsystems": {**board.subsystems, report.subsystem: report}})
