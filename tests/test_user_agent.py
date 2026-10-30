"""The User-Agent names a contact, so a site owner can reach the crawler's operator."""

import pytest
from pydantic import ValidationError

from config.runtime_config import FetchConfig, default_runtime_config
from config.user_agent import has_contact

BROWSER_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "python-requests/2.32",
    "x",
]


@pytest.mark.parametrize(
    "user_agent",
    [
        "Bot/1.0 (+https://example.org/about)",
        "Bot/1.0 (ops@example.org)",
        "Bot/1.0 (research crawler; contact: ops@example.org)",
        "Mozilla/5.0 (compatible; Bot/1.0; +http://example.org/bot.html)",
    ],
)
def test_a_web_or_email_address_counts_as_a_contact(user_agent):
    assert has_contact(user_agent)
    assert FetchConfig(user_agent=user_agent).user_agent == user_agent


@pytest.mark.parametrize("user_agent", BROWSER_USER_AGENTS)
def test_a_user_agent_without_a_contact_is_rejected(user_agent):
    assert not has_contact(user_agent)
    with pytest.raises(ValidationError, match="contact"):
        FetchConfig(user_agent=user_agent)


def test_the_default_user_agent_names_a_contact():
    assert has_contact(default_runtime_config().fetch.user_agent)
