"""The reporter protocol producers are given, and the reporter that discards reports."""

from crawlviz.contracts import LlmFacts
from crawlviz.events import NullStatusReporter, StatusReporter


def test_the_null_reporter_takes_every_form_of_report() -> None:
    reporter: StatusReporter = NullStatusReporter()

    reporter.report("embedder", "starting", "loading_model")
    reporter.report("llm", "waiting", "rate_limited", LlmFacts(calls=3), retry_at=120.0)
