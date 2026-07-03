from dataclasses import dataclass

@dataclass
class ObservabilityEvent:
    type: str
    correlation_id: str
    timestamp: float
    payload: dict
    metadata: dict