
from dataclasses import dataclass
from typing import Any


@dataclass
class ScoreRescheduledEvent:
    correlation_id: str
    node: Any


@dataclass
class RetryOperationFailedEvent:
    correlation_id: str
    stage: str
    error_type: Any
    error_message: str


