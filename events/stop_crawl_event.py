from dataclasses import dataclass
from typing import Optional


@dataclass
class StopCrawlEvent:
    reason: str

    node_count: int
    max_depth: int
    duration: float

    detail: Optional[str] = None