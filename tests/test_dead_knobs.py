import asyncio

import numpy as np

from nlp.buffer_manager import BufferManager
from nlp.expansion_prompt_builder import ExpansionConfig, ExpansionPromptBuilder
from nlp.space_updater import SpaceUpdater


def test_prompt_honours_max_sentences_for_dict_and_dataclass():
    b = ExpansionPromptBuilder()
    p = b.build("cats", {"num_descriptions": 3, "style": "rich", "max_sentences": 4})
    assert "4 sentence(s) max" in p and "Generate 3 " in p
    assert "2 sentence(s) max" in b.build("cats", ExpansionConfig())
    assert "2 sentence(s) max" in b.build("cats")
    assert "Return ONLY valid JSON" in p and '"target"' in p


class _Space:
    version = 0

    def __init__(self):
        self.n = 0

    def add_vector(self, *a):
        self.n += 1


class _Nlp:
    def __init__(self):
        self.space = _Space()

    def save_space(self):
        pass

    def space_size(self):
        return self.space.n


def test_threshold_triggers_flush_before_interval():
    async def run():
        buf = BufferManager(max_size=100)
        nlp = _Nlp()
        up = SpaceUpdater(nlp, buf, flush_interval=3600, flush_threshold=3)
        task = asyncio.create_task(up.start())
        await buf.add_batch([(f"k{i}", np.zeros(2), {}) for i in range(3)])
        for _ in range(40):
            if nlp.space.n == 3:
                break
            await asyncio.sleep(0.1)
        early = nlp.space.n
        up.stop()
        await task
        return early

    assert asyncio.run(run()) == 3
