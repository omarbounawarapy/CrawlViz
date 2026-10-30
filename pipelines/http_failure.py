"""What a failed HTTP fetch tells the crawler: whether to back off, for how long, and
whether trying again can help."""

import email.utils
import math
import time
from datetime import UTC

import aiohttp

HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_REQUEST_TIMEOUT = 408
HTTP_CLIENT_ERROR_MIN = 400
HTTP_SERVER_ERROR_MIN = 500

# The site is asking the crawler to slow down.
BACKOFF_STATUSES = frozenset({HTTP_TOO_MANY_REQUESTS, HTTP_SERVICE_UNAVAILABLE})
# Client errors that can pass on their own; every other 4xx will answer the same again.
RETRYABLE_CLIENT_STATUSES = frozenset({HTTP_REQUEST_TIMEOUT, HTTP_TOO_MANY_REQUESTS})
# A Retry-After longer than this is obeyed up to this long, so one header cannot stall
# a host for the rest of the crawl.
MAX_RETRY_AFTER_SECONDS = 300.0


def status_of(error: BaseException) -> int | None:
    """The HTTP status carried by a failed fetch; None when no response arrived."""
    return error.status if isinstance(error, aiohttp.ClientResponseError) else None


def is_permanent_failure(status: int | None) -> bool:
    """True for a 4xx that retrying cannot fix (404, 403, 410 ...)."""
    return (
        status is not None
        and HTTP_CLIENT_ERROR_MIN <= status < HTTP_SERVER_ERROR_MIN
        and status not in RETRYABLE_CLIENT_STATUSES
    )


def retry_after_seconds(error: BaseException, now: float | None = None) -> float | None:
    """The wait a failed response asked for with Retry-After, capped; None when absent
    or unreadable. The header is a number of seconds or an HTTP date."""
    if not isinstance(error, aiohttp.ClientResponseError) or error.headers is None:
        return None
    value = error.headers.get("Retry-After")
    if value is None:
        return None
    value = value.strip()
    if value.isdigit():
        seconds = float(value)
    else:
        try:
            when = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        seconds = when.timestamp() - (time.time() if now is None else now)
    if not math.isfinite(seconds):
        return None
    return min(max(seconds, 0.0), MAX_RETRY_AFTER_SECONDS)
