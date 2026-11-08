"""The rule for the crawler's User-Agent: it names the crawler and says how to reach its operator.

Site owners read the User-Agent in their logs to decide whether to block a crawler or write
to its operator, so a crawl on a live site must identify its operator and say how to reach them.
"""

import re

# A web address or an email address, anywhere in the text. Both are what site owners
# look for in a crawler's User-Agent, e.g. "Bot/1.0 (+https://example.org/bot; ops@example.org)".
_WEB_ADDRESS = r"https?://[^\s;,()<>]+"
_EMAIL_ADDRESS = r"[^\s@;,()<>]+@[^\s@;,()<>]+\.[A-Za-z]{2,}"
CONTACT_PATTERN = re.compile(f"{_WEB_ADDRESS}|{_EMAIL_ADDRESS}")

CONTACT_REQUIRED_MESSAGE = (
    "The User-Agent must include a contact so site owners can reach you: add a web address or "
    "an email address, for example 'MyCrawler/1.0 (+https://example.org/about; you@example.org)'."
)


def has_contact(user_agent: str) -> bool:
    """True if `user_agent` holds a web address or an email address."""
    return CONTACT_PATTERN.search(user_agent) is not None


def require_contact(user_agent: str) -> str:
    """`user_agent` unchanged, or a ValueError that says how to fix it."""
    if not has_contact(user_agent):
        raise ValueError(CONTACT_REQUIRED_MESSAGE)
    return user_agent
