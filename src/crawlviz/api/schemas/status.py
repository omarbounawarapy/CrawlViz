"""Reply of ``GET /status``: the crawl's lifecycle, its status board and its LLM budget.

The first five fields are the reply the Run page reads today, unchanged: ``llm_calls`` is
``CallBudget.snapshot()`` (``tests/test_run_status.py`` pins it). The rest are added by
ADR 8 and default to null until the crawl controller fills them, so a client that reads
only the first five keeps working.
"""

from pydantic import BaseModel, ConfigDict, NonNegativeInt

from crawlviz.contracts import CrawlEndState, CrawlState, StatusBoardSnapshot


class _Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LlmCallsSnapshot(_Reply):
    """The crawl's LLM call budget: the cap (null for none), calls used and refused."""

    limit: NonNegativeInt | None
    used: NonNegativeInt
    refused: NonNegativeInt
    exhausted: bool


class QueueDepth(_Reply):
    """Items waiting in one stage's queue, and its capacity (null when unbounded)."""

    size: NonNegativeInt
    max: NonNegativeInt | None


class CrawlFailure(_Reply):
    """Why the last crawl failed: the exception class and what to do, never its text."""

    error_type: str
    message: str


class CrawlStatusReply(_Reply):
    """Whether a crawl runs, how the last one ended, and each subsystem's state.

    ``queues`` is keyed by the Pipelines setting name of each stage. ``board`` is null
    before the first crawl starts; after a crawl it keeps that crawl's last board until
    the next one starts (ADR 8).
    """

    running: bool
    llm_calls: LlmCallsSnapshot | None
    queues: dict[str, QueueDepth] | None
    last_outcome: CrawlEndState | None
    last_error: CrawlFailure | None
    crawl_state: CrawlState | None = None
    crawl_id: str | None = None
    board: StatusBoardSnapshot | None = None
