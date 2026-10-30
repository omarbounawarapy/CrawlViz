from core.manifest_redaction import REDACTED, redact_manifest


def test_extra_header_values_are_redacted_and_names_kept() -> None:
    manifest = {
        "runtime_config": {
            "fetch": {
                "user_agent": "Bot/1 (+mailto:ops@example.org)",
                "extra_headers": {"Authorization": "Bearer abc123", "X-Team": "blue"},
            }
        }
    }

    cleaned = redact_manifest(manifest)

    headers = cleaned["runtime_config"]["fetch"]["extra_headers"]
    assert headers == {"Authorization": REDACTED, "X-Team": REDACTED}
    assert cleaned["runtime_config"]["fetch"]["user_agent"] == "Bot/1 (+mailto:ops@example.org)"


def test_secret_looking_keys_are_redacted_anywhere() -> None:
    manifest = {
        "blueprint": {"source": {"headers": {"Cookie": "session=1", "Accept": "text/html"}}},
        "llm_model": {"provider": "groq", "api_key": "sk-secret", "list": [{"x-api-key": "k"}]},
    }

    cleaned = redact_manifest(manifest)

    assert cleaned["blueprint"]["source"]["headers"] == {
        "Cookie": REDACTED,
        "Accept": "text/html",
    }
    assert cleaned["llm_model"]["api_key"] == REDACTED
    assert cleaned["llm_model"]["list"] == [{"x-api-key": REDACTED}]
    assert cleaned["llm_model"]["provider"] == "groq"


def test_counts_named_tokens_are_kept() -> None:
    manifest = {"runtime_config": {"llm": {"max_tokens": 512}}}

    assert redact_manifest(manifest) == manifest


def test_input_is_not_modified() -> None:
    manifest = {"runtime_config": {"fetch": {"extra_headers": {"Cookie": "a=b"}}}}

    redact_manifest(manifest)

    assert manifest["runtime_config"]["fetch"]["extra_headers"] == {"Cookie": "a=b"}
