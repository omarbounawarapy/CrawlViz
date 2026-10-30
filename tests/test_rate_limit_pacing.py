"""RequestsPipeline paces requests per host, even with several workers."""

import asyncio
import time
from itertools import pairwise
from typing import Any

from core.event_broker import EventBroker
from models import Domain, Node
from pipelines.requests_pipeline import RequestsPipeline

MIN_DELAY = 0.05
# Timer granularity: a gap this far under the delay still counts as honoured.
TOLERANCE = 0.01


class TimingFetcher:
    """Records when each URL was requested."""

    def __init__(self) -> None:
        self.times: dict[str, list[float]] = {}

    async def emit_request(self, params: dict[str, Any]) -> str:
        self.times.setdefault(params["url"].split("/")[2], []).append(time.monotonic())
        return "<html></html>"

    async def close(self) -> None:
        pass


def make_node(node_id: int, host: str) -> Node:
    domain = Domain("test", f"http://{host}", ".//a")
    return Node(node_id, url=f"http://{host}/p{node_id}", domain=domain)


async def fetch_all(nodes: list[Node], workers: int) -> dict[str, list[float]]:
    fetcher = TimingFetcher()
    pipeline = RequestsPipeline(
        EventBroker(), max_concurrency=workers, fetcher=fetcher, min_delay=MIN_DELAY, jitter_max=0
    )
    for node in nodes:
        await pipeline.queue.put(node)
    task = asyncio.create_task(pipeline.start())
    deadline = time.monotonic() + 5
    while sum(map(len, fetcher.times.values())) < len(nodes) and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    await pipeline.stop()
    await task
    return fetcher.times


def gaps(times: list[float]) -> list[float]:
    return [later - earlier for earlier, later in pairwise(sorted(times))]


async def test_concurrent_workers_keep_the_delay_between_requests_to_one_host():
    nodes = [make_node(i, "a.test") for i in range(4)]
    times = await fetch_all(nodes, workers=4)
    assert len(times["a.test"]) == 4
    assert min(gaps(times["a.test"])) >= MIN_DELAY - TOLERANCE


async def test_different_hosts_do_not_wait_for_each_other():
    nodes = [make_node(0, "a.test"), make_node(1, "b.test")]
    times = await fetch_all(nodes, workers=2)
    assert abs(times["a.test"][0] - times["b.test"][0]) < MIN_DELAY
