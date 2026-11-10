"""Builds the crawl's UI bridge: the WebSocket gateway, the event recorder and the
telemetry bridge that turns crawl events into UI messages."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.runtime_config import RuntimeConfig
from ui_bridge import CrawlStateSnapshot, KeepAlive, TelemetryBridge, UIWebSocketGateway
from ui_bridge.event_recorder import EventRecorder, RecordingGateway

from .event_broker import EventBroker
from .manifest_redaction import redact_manifest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunRecord:
    """What the event recorder writes about the run, and where."""

    run_dir: Path
    # Recorded as JSON, after secrets are redacted.
    manifest: dict[str, Any]


def build_ui_layer(
    *,
    config: RuntimeConfig,
    ui_port: int,
    event_broker: EventBroker,
    priority_strategy: str,
    record: RunRecord,
) -> RecordingGateway:
    """Build the UI bridge: the WebSocket gateway, the event recorder
    and the TelemetryBridge, subscribed to every event it translates."""
    obs = config.observability
    snapshot = CrawlStateSnapshot(
        max_candidates=obs.snapshot_max_candidates, max_errors=obs.snapshot_max_errors
    )
    ui_gateway = UIWebSocketGateway(
        snapshot,
        KeepAlive(obs.ui_ping_interval, obs.ui_ping_timeout),
        host="localhost",
        port=ui_port,
    )
    recorder = EventRecorder(record.run_dir)
    try:
        recorder.record(snapshot.to_full_snapshot())
        recorder.write_manifest(redact_manifest(record.manifest))
        recording_gateway = RecordingGateway(ui_gateway, recorder)
        telemetry = TelemetryBridge(
            snapshot, recording_gateway, priority_strategy_name=priority_strategy
        )
        telemetry.register_handlers()
        event_broker.subscribe(telemetry, telemetry.event_types)
    except BaseException:
        # Nothing owns the open event log yet, so nothing else would close it.
        _close_after_failure(recorder)
        raise
    # Stopping this one closes the event log as well as the server.
    return recording_gateway


def _close_after_failure(recorder: EventRecorder) -> None:
    """Close the event log without letting a failure to close hide the error that
    is being handled: that one is re-raised by the caller, this one is logged."""
    try:
        recorder.close()
    except Exception:
        logger.exception(
            "Could not close the event log %s after the UI layer failed to build",
            recorder.events_path,
        )
