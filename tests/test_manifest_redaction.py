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


def test_a_cookie_key_is_redacted_and_its_sibling_kept() -> None:
    manifest = {
        "blueprint": {"source": {"headers": {"Cookie": "session=1", "Accept": "text/html"}}}
    }

    cleaned = redact_manifest(manifest)

    assert cleaned["blueprint"]["source"]["headers"] == {
        "Cookie": REDACTED,
        "Accept": "text/html",
    }


def test_an_api_key_is_redacted() -> None:
    cleaned = redact_manifest({"llm_model": {"api_key": "sk-secret"}})

    assert cleaned == {"llm_model": {"api_key": REDACTED}}


def test_an_x_api_key_header_inside_a_list_is_redacted() -> None:
    cleaned = redact_manifest({"requests": [{"x-api-key": "k"}]})

    assert cleaned == {"requests": [{"x-api-key": REDACTED}]}


def test_a_password_is_redacted() -> None:
    cleaned = redact_manifest({"login": {"password": "hunter2"}})

    assert cleaned == {"login": {"password": REDACTED}}


def test_a_key_with_no_secret_in_its_name_is_kept() -> None:
    manifest = {"llm_model": {"name": "example-model"}}

    assert redact_manifest(manifest) == manifest


def test_counts_named_tokens_are_kept() -> None:
    manifest = {"runtime_config": {"llm": {"max_tokens": 512}}}

    assert redact_manifest(manifest) == manifest


def test_input_is_not_modified() -> None:
    manifest = {"runtime_config": {"fetch": {"extra_headers": {"Cookie": "a=b"}}}}

    redact_manifest(manifest)

    assert manifest["runtime_config"]["fetch"]["extra_headers"] == {"Cookie": "a=b"}
