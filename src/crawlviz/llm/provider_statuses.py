"""HTTP statuses a provider answers with that the LLM layer treats apart from the rest."""

from typing import Final

TOO_MANY_REQUESTS: Final = 429
SERVER_ERROR_STATUSES: Final = range(500, 600)
# The key was refused; it will not start working, so it leaves the rotation.
REJECTED_KEY_STATUSES: Final = frozenset({401, 403})
