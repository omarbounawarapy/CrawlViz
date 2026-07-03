import os
from typing import Any


# Events that are ALWAYS emitted regardless of mode
_FORCE_EMIT_SUFFIXES = ("Failed", "Bootstrapped", "ScoreEmitted")

# Minimal-mode allowlist — only these event type names pass in "minimal" mode
_MINIMAL_ALLOWLIST = frozenset({
    "NLP_ScoreEmitted",
    "LLM_RequestFailed",
    "NET_RequestFailed",
    "EXP_SpaceBootstrapped",
})


class TraceEmitter:
    """
    Thin publish wrapper around the existing event_broker.
    Respects TRACE_MODE without touching any pipeline or business logic.

    Modes
    -----
    full     — emit everything (default for DEBUG=True)
    sampled  — emit 1-in-N per link, but always emit failures
    minimal  — emit only terminal/failure events (production default)
    off      — emit nothing
    """

    def __init__(self, event_broker, mode: str = "full", sample_rate: float = 0.1):
        self._broker = event_broker
        self.mode = mode
        self.sample_rate = max(0.0001, min(1.0, sample_rate))
        self._counter = 0

    # ------------------------------------------------------------------
    async def emit(self, event: Any) -> None:
        if self.mode == "off":
            return

        event_name = type(event).__name__

        # Failures always pass through
        is_critical = any(event_name.endswith(s) for s in _FORCE_EMIT_SUFFIXES)

        if self.mode == "minimal":
            if not is_critical and event_name not in _MINIMAL_ALLOWLIST:
                return

        elif self.mode == "sampled":
            if not is_critical:
                self._counter += 1
                step = max(1, round(1.0 / self.sample_rate))
                if self._counter % step != 0:
                    return

        # "full" always falls through
        await self._broker.emit(event)

    # ------------------------------------------------------------------
    @classmethod
    def from_env(cls, event_broker) -> "TraceEmitter":
        """
        Construct from environment variables.
        TRACE_MODE = full | sampled | minimal | off   (default: full)
        TRACE_SAMPLE_RATE = 0.0–1.0                   (default: 0.1)
        """
        mode = os.getenv("TRACE_MODE", "full").lower()
        rate = float(os.getenv("TRACE_SAMPLE_RATE", "0.1"))
        return cls(event_broker, mode=mode, sample_rate=rate)