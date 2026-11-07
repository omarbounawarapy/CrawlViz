"""TracedLlmHandler's trace events carry what the wrapped call used."""

from models import ScoringContext
from traceability import LLM_ResponseParsed, TracedLlmHandler

REPLY = {"results": {"a": 0.5}}


class UsageReportingLlm:
    """Answers like LlmHandler does: the parsed reply, the usage on the context."""

    async def send(self, context: ScoringContext) -> dict[str, object]:
        context.set_usage(120, 30)
        return REPLY


class RecordingTracer:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def emit(self, event: object) -> None:
        self.events.append(event)


async def test_the_parsed_event_carries_the_calls_token_usage() -> None:
    tracer = RecordingTracer()
    traced = TracedLlmHandler(UsageReportingLlm(), tracer)  # type: ignore[arg-type]

    assert await traced.send(ScoringContext("openai", "m", "prompt")) == REPLY

    [parsed] = [event for event in tracer.events if isinstance(event, LLM_ResponseParsed)]
    assert parsed.token_usage == {"input_tokens": 120, "output_tokens": 30}
    assert parsed.output_keys == ["results"]
