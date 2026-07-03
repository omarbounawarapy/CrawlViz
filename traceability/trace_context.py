import uuid
from contextvars import ContextVar

_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_node_id: ContextVar[str] = ContextVar("node_id", default="")


def set_trace(trace_id: str, node_id: str) -> None:
    _trace_id.set(trace_id)
    _node_id.set(node_id)


def get_trace() -> tuple[str, str]:
    return _trace_id.get(), _node_id.get()


def new_trace_id() -> str:
    return uuid.uuid4().hex[:12]