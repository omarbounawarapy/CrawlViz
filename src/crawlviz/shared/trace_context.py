"""Per-task trace context: the (trace_id, node_id) pair that every
traceability event is stamped with, threaded implicitly through
asyncio tasks via contextvars rather than passed as an explicit
parameter down every call chain.
"""

import uuid
from contextvars import ContextVar

_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_node_id: ContextVar[str] = ContextVar("node_id", default="")


def set_trace(trace_id: str, node_id: str) -> None:
    """Bind `trace_id`/`node_id` to the current task's context."""
    _trace_id.set(trace_id)
    _node_id.set(node_id)


def get_trace() -> tuple[str, str]:
    """Return the current task's (trace_id, node_id), or ("", "") if unset."""
    return _trace_id.get(), _node_id.get()


def new_trace_id() -> str:
    """Generate a fresh, short trace identifier."""
    return uuid.uuid4().hex[:12]


def bind_node(node_id: str) -> str:
    """Bind a trace to `node_id` for the current task and return its id.

    The trace id is derived from the node id, so every pipeline stage that
    handles the same node stamps its events with the same trace.
    """
    trace_id = uuid.uuid5(uuid.NAMESPACE_URL, f"node:{node_id}").hex[:12]
    set_trace(trace_id, node_id)
    return trace_id
