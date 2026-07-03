from dataclasses import dataclass


@dataclass
class ExportBatchStartedEvent:
    correlation_id: str
    table: str
    batch_size: int


@dataclass
class ExportBatchCompletedEvent:
    correlation_id: str
    table: str
    inserted_count: int
    duration_ms: float


@dataclass
class ExportBatchFailedEvent:
    correlation_id: str
    table: str
    error_type: str
    error_message: str


@dataclass
class ExportRowFailedEvent:
    correlation_id: str
    table: str
    field: str
    value: str
    error_type: str