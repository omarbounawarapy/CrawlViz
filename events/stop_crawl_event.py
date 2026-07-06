from dataclasses import dataclass
from typing import Literal


@dataclass
class StopCrawlEvent:
    reason: Literal[
        "MAX_NODES_REACHED",
        "MAX_DEPTH_REACHED",
        "TARGET_REACHED",
        "TIME_LIMIT_REACHED",
        "NO_PROGRESS",
    ]
    node_count: int
    max_depth: int
    duration: float
    detail: str | None = None
