"""A provider endpoint is stored in the settings file, the run manifest and the UI, so it
must not hold a credential. Keys belong in the keys store (SEC-3)."""

import pytest
from pydantic import ValidationError

from config.runtime_config import ProvidersConfig, RuntimeConfig

FAKE_KEY = "FAKEKEY-0123456789"


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://user:hunter2@api.example/v1/chat",
        "https://user@api.example/v1/chat",
        f"https://api.example/v1/chat?key={FAKE_KEY}",
        f"https://api.example/v1/chat?alt=sse&api_key={FAKE_KEY}",
        f"https://api.example/v1/chat?token={FAKE_KEY}",
    ],
)
def test_an_endpoint_with_a_credential_is_refused_with_advice(endpoint: str) -> None:
    with pytest.raises(ValidationError) as caught:
        ProvidersConfig(endpoints={"openai": endpoint})

    message = str(caught.value)
    assert "openai" in message
    assert "keys" in message.lower()
    assert FAKE_KEY not in message
    assert "hunter2" not in message


def test_a_refused_endpoint_is_not_echoed_when_the_whole_config_is_validated() -> None:
    values = {"providers": {"endpoints": {"openai": f"https://api.example/v1?key={FAKE_KEY}"}}}

    with pytest.raises(ValidationError) as caught:
        RuntimeConfig.model_validate(values)

    assert FAKE_KEY not in str(caught.value)


def test_an_endpoint_without_a_credential_is_accepted() -> None:
    config = ProvidersConfig(endpoints={"openai": "http://localhost:11434/v1/chat?model=llama"})

    assert config.endpoints["openai"].startswith("http://localhost")
