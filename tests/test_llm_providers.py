"""Coverage for the OpenAI/Anthropic/Gemini translators added alongside the
existing OpenRouter integration, and for their wiring into LlmHandler.

Mirrors the style of test_results_mapper.py: translators are pure static
methods (translate_request/translate_response), so most of this is direct
unit testing with fake, lightweight stand-ins -- no real API keys, no real
network calls. The end-to-end tests at the bottom fake only NetworkClient
and KeyManager, to prove each new provider is actually reachable through
LlmHandler.send(), not just implemented as an unused class.
"""
from models import ExpansionContext, ScoringContext

from infrastructure import (
    AnthropicTranslator,
    GeminiTranslator,
    KeyManager,
    LlmHandler,
    NvidiaTranslator,
    OpenAITranslator,
    OpenRouterTranslator,
)


class FakeNetworkClient:
    """Stands in for infrastructure.NetworkClient: records the params it
    was called with and returns a preset canned response instead of
    making a real HTTP request.
    """

    def __init__(self, canned_response):
        self.canned_response = canned_response
        self.last_params = None

    async def emit_request(self, params):
        self.last_params = params
        return self.canned_response


def make_key_manager(monkeypatch, keys: dict) -> KeyManager:
    """Builds a real KeyManager without touching keys.json on disk."""
    monkeypatch.setattr(KeyManager, "load_keys", lambda self: keys)
    return KeyManager()


# =====================================================================
# Provider selection
# =====================================================================

class TestProviderSelection:
    def test_all_five_providers_registered(self):
        assert LlmHandler.translators == {
            "openrouter": OpenRouterTranslator,
            "openai": OpenAITranslator,
            "anthropic": AnthropicTranslator,
            "gemini": GeminiTranslator,
            "nvidia": NvidiaTranslator,
        }

    async def test_unknown_provider_raises_before_any_request_is_sent(self, monkeypatch):
        key_manager = make_key_manager(monkeypatch, {})
        fake_client = FakeNetworkClient(canned_response={})
        handler = LlmHandler(key_manager, client=fake_client)

        ctx = ScoringContext("not-a-real-provider", "some-model", "prompt")

        try:
            await handler.send(ctx)
            raise AssertionError("expected ValueError for an unregistered provider")
        except ValueError as e:
            assert "not-a-real-provider" in str(e)

        # The existing, unmodified behavior: translation happens before any
        # network call, so an unknown provider never reaches the client.
        assert fake_client.last_params is None


# =====================================================================
# OpenAI
# =====================================================================

class TestOpenAITranslator:
    def test_translate_request_shape(self):
        ctx = ScoringContext("openai", "gpt-4o-mini", "score these links")
        ctx.set_key("sk-test-openai-key")

        params = OpenAITranslator.translate_request(ctx)

        assert params["method"] == "POST"
        assert params["url"] == "https://api.openai.com/v1/chat/completions"
        assert params["headers"]["Authorization"] == "Bearer sk-test-openai-key"
        assert params["data"]["model"] == "gpt-4o-mini"
        assert params["data"]["messages"] == [
            {"role": "user", "content": "score these links"}
        ]

    def test_translate_response_plain_json(self):
        response = {
            "choices": [
                {"message": {"content": '{"results": {"https://a.com": {"score": 90}}}'}}
            ]
        }
        assert OpenAITranslator.translate_response(response) == {
            "results": {"https://a.com": {"score": 90}}
        }

    def test_translate_response_strips_markdown_fences(self):
        response = {
            "choices": [{"message": {"content": '```json\n{"descriptions": ["a", "b"]}\n```'}}]
        }
        assert OpenAITranslator.translate_response(response) == {
            "descriptions": ["a", "b"]
        }

    def test_translate_response_malformed_yields_empty_dict(self):
        assert OpenAITranslator.translate_response({"unexpected": "shape"}) == {}
        assert OpenAITranslator.translate_response(
            {"choices": [{"message": {"content": "not json at all"}}]}
        ) == {}


# =====================================================================
# Anthropic
# =====================================================================

class TestAnthropicTranslator:
    def test_translate_request_shape(self):
        ctx = ScoringContext("anthropic", "claude-3-5-sonnet-latest", "score these links")
        ctx.set_key("sk-ant-test-key")

        params = AnthropicTranslator.translate_request(ctx)

        assert params["method"] == "POST"
        assert params["url"] == "https://api.anthropic.com/v1/messages"
        # Anthropic auth is x-api-key, NOT an Authorization/Bearer header.
        assert params["headers"]["x-api-key"] == "sk-ant-test-key"
        assert "Authorization" not in params["headers"]
        assert params["headers"]["anthropic-version"] == "2023-06-01"
        assert params["data"]["model"] == "claude-3-5-sonnet-latest"
        # max_tokens is required by Anthropic's API; CrawlViz's contexts
        # don't carry one, so the translator must supply a default.
        assert params["data"]["max_tokens"] == AnthropicTranslator.DEFAULT_MAX_TOKENS
        assert params["data"]["messages"] == [
            {"role": "user", "content": "score these links"}
        ]

    def test_translate_response_single_text_block(self):
        response = {
            "content": [
                {"type": "text", "text": '{"results": {"https://a.com": {"score": 42}}}'}
            ]
        }
        assert AnthropicTranslator.translate_response(response) == {
            "results": {"https://a.com": {"score": 42}}
        }

    def test_translate_response_joins_multiple_text_blocks(self):
        response = {
            "content": [
                {"type": "text", "text": '{"descriptions": '},
                {"type": "text", "text": '["a", "b"]}'},
            ]
        }
        assert AnthropicTranslator.translate_response(response) == {
            "descriptions": ["a", "b"]
        }

    def test_translate_response_strips_markdown_fences(self):
        response = {"content": [{"type": "text", "text": '```json\n{"score": 1}\n```'}]}
        assert AnthropicTranslator.translate_response(response) == {"score": 1}

    def test_translate_response_malformed_yields_empty_dict(self):
        assert AnthropicTranslator.translate_response({"content": []}) == {}
        assert AnthropicTranslator.translate_response(
            {"content": [{"type": "text", "text": "not json"}]}
        ) == {}
        assert AnthropicTranslator.translate_response(
            {"type": "error", "error": {"message": "overloaded"}}
        ) == {}


# =====================================================================
# Gemini
# =====================================================================

class TestGeminiTranslator:
    def test_translate_request_shape(self):
        ctx = ScoringContext("gemini", "gemini-1.5-flash", "score these links")
        ctx.set_key("gm-test-key")

        params = GeminiTranslator.translate_request(ctx)

        assert params["method"] == "POST"
        # Model is embedded in the URL path, not a body field.
        assert params["url"] == (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-1.5-flash:generateContent"
        )
        assert "model" not in params["data"]
        assert params["headers"]["x-goog-api-key"] == "gm-test-key"
        assert "Authorization" not in params["headers"]
        assert params["data"]["contents"] == [
            {"parts": [{"text": "score these links"}]}
        ]

    def test_translate_response_single_part(self):
        response = {
            "candidates": [
                {"content": {"parts": [{"text": '{"results": {"https://a.com": {"score": 7}}}'}]}}
            ]
        }
        assert GeminiTranslator.translate_response(response) == {
            "results": {"https://a.com": {"score": 7}}
        }

    def test_translate_response_joins_multiple_parts(self):
        response = {
            "candidates": [
                {"content": {"parts": [{"text": '{"descriptions": ['}, {"text": '"a"]}'}]}}
            ]
        }
        assert GeminiTranslator.translate_response(response) == {"descriptions": ["a"]}

    def test_translate_response_empty_candidates_yields_empty_dict(self):
        # e.g. a prompt blocked by safety filtering comes back with no candidates.
        assert GeminiTranslator.translate_response({"candidates": []}) == {}

    def test_translate_response_malformed_yields_empty_dict(self):
        assert GeminiTranslator.translate_response({"unexpected": "shape"}) == {}


# =====================================================================
# NVIDIA (NIM)
# =====================================================================

class TestNvidiaTranslator:
    def test_translate_request_shape(self):
        ctx = ScoringContext("nvidia", "meta/llama-3.1-70b-instruct", "score these links")
        ctx.set_key("nvapi-test-key")

        params = NvidiaTranslator.translate_request(ctx)

        assert params["method"] == "POST"
        assert params["url"] == "https://integrate.api.nvidia.com/v1/chat/completions"
        assert params["headers"]["Authorization"] == "Bearer nvapi-test-key"
        assert params["data"]["model"] == "meta/llama-3.1-70b-instruct"
        assert params["data"]["messages"] == [
            {"role": "user", "content": "score these links"}
        ]

    def test_translate_response_plain_json(self):
        response = {
            "choices": [
                {"message": {"content": '{"results": {"https://a.com": {"score": 33}}}'}}
            ]
        }
        assert NvidiaTranslator.translate_response(response) == {
            "results": {"https://a.com": {"score": 33}}
        }

    def test_translate_response_strips_markdown_fences(self):
        response = {
            "choices": [{"message": {"content": '```json\n{"descriptions": ["c"]}\n```'}}]
        }
        assert NvidiaTranslator.translate_response(response) == {"descriptions": ["c"]}

    def test_translate_response_malformed_yields_empty_dict(self):
        assert NvidiaTranslator.translate_response({"unexpected": "shape"}) == {}
        assert NvidiaTranslator.translate_response(
            {"choices": [{"message": {"content": "not json at all"}}]}
        ) == {}


# =====================================================================
# End-to-end through LlmHandler.send() -- proves reachability, not just
# that the classes exist.
# =====================================================================

class TestEndToEndThroughLlmHandler:
    async def test_openai_reachable_via_scoring_context(self, monkeypatch):
        key_manager = make_key_manager(monkeypatch, {"openai": ["sk-test"]})
        fake_client = FakeNetworkClient({
            "choices": [{"message": {"content": '{"results": {"https://a.com": {"score": 5}}}'}}]
        })
        handler = LlmHandler(key_manager, client=fake_client)

        ctx = ScoringContext("openai", "gpt-4o-mini", "score these links")
        result = await handler.send(ctx)

        assert result == {"results": {"https://a.com": {"score": 5}}}
        assert fake_client.last_params["url"] == "https://api.openai.com/v1/chat/completions"
        assert fake_client.last_params["headers"]["Authorization"] == "Bearer sk-test"

    async def test_anthropic_reachable_via_expansion_context(self, monkeypatch):
        key_manager = make_key_manager(monkeypatch, {"anthropic": ["sk-ant-test"]})
        fake_client = FakeNetworkClient({
            "content": [{"type": "text", "text": '{"descriptions": ["expanded topic"]}'}]
        })
        handler = LlmHandler(key_manager, client=fake_client)

        ctx = ExpansionContext("anthropic", "claude-3-5-sonnet-latest", "expand this topic")
        result = await handler.send(ctx)

        assert result == {"descriptions": ["expanded topic"]}
        assert fake_client.last_params["headers"]["x-api-key"] == "sk-ant-test"

    async def test_gemini_reachable_via_scoring_context(self, monkeypatch):
        key_manager = make_key_manager(monkeypatch, {"gemini": ["gm-test"]})
        fake_client = FakeNetworkClient({
            "candidates": [{"content": {"parts": [{"text": '{"results": {}}'}]}}]
        })
        handler = LlmHandler(key_manager, client=fake_client)

        ctx = ScoringContext("gemini", "gemini-1.5-flash", "score these links")
        result = await handler.send(ctx)

        assert result == {"results": {}}
        assert "gemini-1.5-flash:generateContent" in fake_client.last_params["url"]

    async def test_nvidia_reachable_via_scoring_context(self, monkeypatch):
        key_manager = make_key_manager(monkeypatch, {"nvidia": ["nvapi-test"]})
        fake_client = FakeNetworkClient({
            "choices": [{"message": {"content": '{"results": {"https://a.com": {"score": 12}}}'}}]
        })
        handler = LlmHandler(key_manager, client=fake_client)

        ctx = ScoringContext("nvidia", "meta/llama-3.1-70b-instruct", "score these links")
        result = await handler.send(ctx)

        assert result == {"results": {"https://a.com": {"score": 12}}}
        assert fake_client.last_params["url"] == "https://integrate.api.nvidia.com/v1/chat/completions"
        assert fake_client.last_params["headers"]["Authorization"] == "Bearer nvapi-test"

    async def test_provider_without_keys_gets_none_key_not_a_crash(self, monkeypatch):
        # KeyManager.next_key returns None for a provider with no configured
        # keys; LlmHandler still constructs and sends the request (it will
        # fail at the real HTTP layer with an auth error, which is the
        # existing, unmodified error-handling path -- this just proves that
        # path is unchanged by adding new providers).
        key_manager = make_key_manager(monkeypatch, {})
        fake_client = FakeNetworkClient({"choices": [{"message": {"content": "{}"}}]})
        handler = LlmHandler(key_manager, client=fake_client)

        ctx = ScoringContext("openai", "gpt-4o-mini", "score these links")
        await handler.send(ctx)

        assert fake_client.last_params["headers"]["Authorization"] == "Bearer None"
