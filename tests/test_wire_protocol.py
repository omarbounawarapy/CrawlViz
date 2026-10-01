"""Every message type the backend emits is documented in docs/crawl_messages.ts."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EMITTERS = ["ui_bridge/telemetry_bridge.py", "ui_bridge/crawl_state_snapshot.py"]

_EMITTED = re.compile(r'"type":\s*"([A-Z_]+)"')
_DOCUMENTED = re.compile(r'^\s*type:\s*"([A-Z_]+)";', re.MULTILINE)


def _emitted():
    return {t for f in EMITTERS for t in _EMITTED.findall((ROOT / f).read_text())}


def _documented():
    return set(_DOCUMENTED.findall((ROOT / "docs/crawl_messages.ts").read_text()))


def test_every_emitted_message_type_is_documented():
    missing = _emitted() - _documented()
    assert not missing, f"emitted but missing from docs/crawl_messages.ts: {sorted(missing)}"


def test_documented_types_are_all_emitted():
    stale = _documented() - _emitted()
    assert not stale, f"documented but never emitted: {sorted(stale)}"
