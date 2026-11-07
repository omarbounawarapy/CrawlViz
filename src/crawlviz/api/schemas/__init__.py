"""Request and reply models of the HTTP API (CONTRACT-2). Routers declare them as
``response_model``; the OpenAPI document and the generated UI client are built from them."""

from .health import HealthReply, ReadinessCheck, ReadyReply
from .status import CrawlFailure, CrawlStatusReply, LlmCallsSnapshot, QueueDepth

__all__ = [
    "CrawlFailure",
    "CrawlStatusReply",
    "HealthReply",
    "LlmCallsSnapshot",
    "QueueDepth",
    "ReadinessCheck",
    "ReadyReply",
]
