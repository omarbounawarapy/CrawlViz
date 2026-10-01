
from models.node import Node
from pipelines.base_pipeline import SHUTDOWN
from pipelines.frontier_queue import FrontierQueue



def _node(node_id: int, priority: float) -> Node:
    return Node(node_id, url=f"http://x/{node_id}", domain=None, priority=priority)


async def _drain(queue) -> list:
    out = []
    while not queue.empty():
        out.append(await queue.get())
    return out


async def test_highest_priority_pops_first():
    queue = FrontierQueue()
    for node in (_node(0, 0.0), _node(1, 95.0), _node(2, 40.0)):
        await queue.put(node)

    assert [n.get_id() for n in await _drain(queue)] == [1, 2, 0]


async def test_equal_priority_is_fifo():
    queue = FrontierQueue()
    for node_id in range(5):
        await queue.put(_node(node_id, 10.0))

    assert [n.get_id() for n in await _drain(queue)] == [0, 1, 2, 3, 4]


async def test_decreased_priority_demotes_on_requeue():
    queue = FrontierQueue()
    demoted, other = _node(0, 50.0), _node(1, 40.0)
    demoted.decrease_priority(20)
    await queue.put(demoted)
    await queue.put(other)

    assert (await queue.get()) is other


async def test_shutdown_sentinel_pops_before_nodes():
    queue = FrontierQueue()
    await queue.put(_node(0, 99.0))
    await queue.put(SHUTDOWN)

    assert (await queue.get()) is SHUTDOWN
