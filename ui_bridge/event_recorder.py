"""Persist the stream the UI receives.

``RecordingGateway`` sits between ``TelemetryBridge`` and the real
``UIWebSocketGateway``: every message that is broadcast is first appended
to ``<export_dir>/<crawl_id>/events.jsonl``, one JSON object per line, in
broadcast order. The first line is an empty ``SNAPSHOT_FULL`` so the file
is a complete session the frontend reducer can replay unchanged.

``manifest.json`` next to it records what produced the run (blueprint,
config, models, git sha, seed).
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from config.config import BASE_DIR

log = logging.getLogger("ui_bridge.recorder")


def git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=BASE_DIR, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


class EventRecorder:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.run_dir / "events.jsonl"
        self._fh = open(self.events_path, "w", encoding="utf-8")

    def record(self, message: dict) -> None:
        if self._fh is None:
            return
        self._fh.write(json.dumps(message, default=str) + "\n")
        self._fh.flush()

    def write_manifest(self, manifest: dict) -> None:
        path = self.run_dir / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


class RecordingGateway:
    """Records each broadcast, then forwards to the wrapped gateway."""

    def __init__(self, gateway: Any, recorder: EventRecorder) -> None:
        self._gateway = gateway
        self._recorder = recorder

    async def broadcast(self, message: dict) -> None:
        try:
            self._recorder.record(message)
        except Exception:
            log.exception("could not record event")
        await self._gateway.broadcast(message)

    async def stop(self) -> None:
        self._recorder.close()
        await self._gateway.stop()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._gateway, name)
