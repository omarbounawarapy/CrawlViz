import time
from urllib.parse import urlsplit


def host_of(url: str) -> str:
    """The host a politeness limit applies to: scheme-less, lower-case host and port."""
    return urlsplit(url).netloc.lower()


class HostPacer:
    """Hands out request slots per host so workers never fire in the same instant.

    A worker calls `reserve` and sleeps for the returned time. The slot is
    claimed before the sleep, in one step with no `await`, so on one event
    loop two workers can never read the same free slot. That step is the
    lock: the old read, sleep, write pattern let every worker see the same
    idle host and send together.
    """

    def __init__(self) -> None:
        self._next_slot: dict[str, float] = {}

    def reserve(self, host: str, spacing: float, lead: float = 0.0) -> float:
        """Claim the next slot on `host`; return the seconds to wait before using it.

        `spacing` is the minimum gap that must follow this request on the same
        host. `lead` is extra waiting for this request alone (jitter, backoff);
        it counts towards the gap, so jitter can never shrink the spacing.
        """
        now = time.monotonic()
        start = max(now, self._next_slot.get(host, now)) + lead
        self._next_slot[host] = start + spacing
        return start - now

    def hold_off(self, host: str, seconds: float) -> None:
        """Push the next slot on `host` at least `seconds` into the future (Retry-After)."""
        resume = time.monotonic() + seconds
        self._next_slot[host] = max(self._next_slot.get(host, resume), resume)
