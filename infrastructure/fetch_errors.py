"""Errors for requests the fetch policy refuses.

Each one is a decision about the target, not a transient failure, so retrying
the same URL cannot change the answer.
"""


class FetchRejectedError(Exception):
    """A request refused by fetch policy."""


class BlockedAddressError(FetchRejectedError, OSError):
    """The target is a private, loopback, link-local, metadata or otherwise
    non-public address (an `OSError` so aiohttp's connector reports it like any
    other connect failure)."""


class TooManyRedirectsError(FetchRejectedError):
    """A GET followed more redirects than the client allows."""



class ResponseTooLargeError(FetchRejectedError):
    """The body is larger than the client's size limit (counted after decompression)."""


class UnsupportedContentTypeError(FetchRejectedError):
    """The response is not one of the content types the caller can parse."""
