import asyncio

from benchmark.llm_cache import CachedLlm


class _Ctx:
    def get_llm_type(self): return "t"
    def get_model_information(self): return "m"
    def get_prompt(self): return "p"
    def get_usage(self): return (3, 4)


class _Inner:
    def __init__(self, answers): self.answers = list(answers)
    async def send(self, context): return self.answers.pop(0)


def test_empty_then_retry_replays_in_order(tmp_path):
    path = tmp_path / "c.jsonl"
    live = CachedLlm(_Inner([{}, {"ok": 1}]), path)
    got = [asyncio.run(live.send(_Ctx())) for _ in range(2)]
    assert got == [{}, {"ok": 1}]
    replay = CachedLlm(_Inner([]), path, replay_only=True)
    again = [asyncio.run(replay.send(_Ctx())) for _ in range(2)]
    assert again == [{}, {"ok": 1}]
    assert not replay.replay_misses
    assert (replay.input_tokens, replay.output_tokens) == (6, 8)
