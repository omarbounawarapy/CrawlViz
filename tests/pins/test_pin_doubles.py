"""The LLM and gateway doubles of the pin crawl."""
import json

from pin_doubles import RecordingGateway, RecordingLlm, ScriptedLlm

from models import LlmContext


def scoring_context(urls: list[str]) -> LlmContext:
    candidates = json.dumps([{"url": url} for url in urls])
    return LlmContext("kind", "model", f"CANDIDATES:\n{candidates}\nOUTPUT")


async def test_a_prompt_without_candidates_is_answered_as_an_expansion() -> None:
    answer = await ScriptedLlm().send(LlmContext("kind", "model", "describe the topic"))

    assert answer["descriptions"]


async def test_each_candidate_gets_a_score_that_depends_only_on_its_url() -> None:
    urls = ["https://x.test/a", "https://x.test/b"]

    first = await ScriptedLlm().send(scoring_context(urls))
    again = await ScriptedLlm().send(scoring_context(list(reversed(urls))))

    scores = {entry["url"]: entry["score"] for entry in first["results"]}
    assert set(scores) == set(urls)
    assert scores == {entry["url"]: entry["score"] for entry in again["results"]}
    assert all(0 <= score < 100 for score in scores.values())


async def test_the_recording_llm_keeps_the_request_before_passing_it_on() -> None:
    llm = RecordingLlm(ScriptedLlm())

    answer = await llm.send(LlmContext("kind", "model", "prompt"))

    assert llm.requests == [{"llm_type": "kind", "model": "model", "prompt": "prompt"}]
    assert answer["descriptions"]


async def test_the_gateway_keeps_broadcast_messages_in_order() -> None:
    gateway = RecordingGateway()

    await gateway.broadcast({"type": "A"})
    await gateway.broadcast({"type": "B"})
    await gateway.stop()

    assert [message["type"] for message in gateway.messages] == ["A", "B"]
