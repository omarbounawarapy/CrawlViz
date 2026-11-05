"""The shared kernel: code every other area may use and that imports no other area.

Atomic file writes and JSON files, background task tracking, hashing, URL and HTML helpers,
log redaction, the trace context, and the guarded HTTP client with the errors it raises.
Other areas import from `crawlviz.shared`, never from a module inside it (ARCH-2).
"""

from .atomic_write import atomic_open, write_text_atomic
from .background_tasks import BackgroundTasks
from .fetch_errors import (
    REJECTION_ERROR_NAMES,
    BlockedAddressError,
    FetchRejectedError,
    ResponseTooLargeError,
    TooManyRedirectsError,
    UnsupportedContentTypeError,
)
from .git_revision import get_git_revision
from .hash_utils import hash_item
from .html_utils import (
    apply_selector,
    build_url,
    configure_url_normalization,
    document_text,
    is_absolute_url,
    is_relative_url,
    normalize_url,
)
from .jsonio import load_json, save_json
from .log_redaction import (
    MIN_SECRET_LENGTH,
    REDACTED,
    clear_registered_secrets,
    redact_secrets,
    register_provider_keys,
    register_secrets,
)
from .network_client import MAX_REDIRECTS, GetRequestStrategy, NetworkClient
from .trace_context import bind_node, get_trace, new_trace_id, set_trace
from .url_guard import PublicAddressResolver, ensure_public_url, is_blocked_address

__all__ = [
    "MAX_REDIRECTS",
    "MIN_SECRET_LENGTH",
    "REDACTED",
    "REJECTION_ERROR_NAMES",
    "BackgroundTasks",
    "BlockedAddressError",
    "FetchRejectedError",
    "GetRequestStrategy",
    "NetworkClient",
    "PublicAddressResolver",
    "ResponseTooLargeError",
    "TooManyRedirectsError",
    "UnsupportedContentTypeError",
    "apply_selector",
    "atomic_open",
    "bind_node",
    "build_url",
    "clear_registered_secrets",
    "configure_url_normalization",
    "document_text",
    "ensure_public_url",
    "get_git_revision",
    "get_trace",
    "hash_item",
    "is_absolute_url",
    "is_blocked_address",
    "is_relative_url",
    "load_json",
    "new_trace_id",
    "normalize_url",
    "redact_secrets",
    "register_provider_keys",
    "register_secrets",
    "save_json",
    "set_trace",
    "write_text_atomic",
]
