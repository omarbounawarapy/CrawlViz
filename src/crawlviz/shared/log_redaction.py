"""Removes secrets from text before it is written to a log.

Two layers, because a secret reaches a log in two ways:

* Registered values. The code that holds a secret (the API key store, the session token)
  registers it with `register_secrets`, and every exact occurrence is replaced, whatever
  text surrounds it.
* Shapes. Text that looks like a credential is replaced even when it was never registered:
  an ``Authorization: Bearer ...`` header, and ``key=...``, ``token: ...`` or ``password=...``
  pairs such as the ``?key=`` query some providers put in the URL.

`REDACTED` is the one placeholder shared with the run manifest (``core/manifest_redaction.py``).
"""

import re
from collections.abc import Iterable, Mapping

REDACTED = "[redacted]"

# A shorter value is more likely a common word or a number than a credential, and replacing
# it would damage ordinary log text.
MIN_SECRET_LENGTH = 8

_BEARER_TOKEN = re.compile(r"(?P<prefix>\bBearer\s+)[^\s\"',;]+", re.IGNORECASE)
# The name may carry a prefix ("X-Api-Key", "access_token"). The match starts only where a
# name starts and the prefix is bounded, so a long word costs linear time, not quadratic.
MAX_NAME_PREFIX_CHARS = 64
_CREDENTIAL_PAIR = re.compile(
    rf"(?P<prefix>(?<![\w-])[\w-]{{0,{MAX_NAME_PREFIX_CHARS}}}?"
    r"(?:api[-_]?key|key|token|secret|passw(?:or)?d|authorization)"
    r"[\"']?\s*[:=]\s*[\"']?)"
    rf"[^\s&\"',;]{{{MIN_SECRET_LENGTH},}}",
    re.IGNORECASE,
)

_registered_secrets: set[str] = set()


def register_secrets(values: Iterable[str]) -> None:
    """Replace every later occurrence of each value in log text. Short values are ignored."""
    _registered_secrets.update(value for value in values if len(value) >= MIN_SECRET_LENGTH)


def register_provider_keys(registry: Mapping[str, Iterable[str]]) -> None:
    """Register every key of a ``{provider: [key, ...]}`` registry (``KeyManager.registry``)."""
    register_secrets(key for keys in registry.values() for key in keys)


def clear_registered_secrets() -> None:
    """Forget every registered value; for tests, which must not leak secrets between cases."""
    _registered_secrets.clear()


def redact_secrets(text: str) -> str:
    """`text` with registered secret values and credential-shaped text replaced."""
    # Longest first, so a secret that contains another one is replaced whole.
    for secret in sorted(_registered_secrets, key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    text = _BEARER_TOKEN.sub(rf"\g<prefix>{REDACTED}", text)
    return _CREDENTIAL_PAIR.sub(rf"\g<prefix>{REDACTED}", text)
