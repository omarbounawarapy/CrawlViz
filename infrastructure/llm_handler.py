import aiohttp

from .anthropic_translator import AnthropicTranslator
from .gemini_translator import GeminiTranslator
from .groq_translator import GroqTranslator
from .key_manager import KeyManager
from .network_client import NetworkClient
from .nvidia_translator import NvidiaTranslator
from .open_router_translator import OpenRouterTranslator
from .openai_translator import OpenAITranslator


class LlmHandler:
    """Routes LLM requests through the correct translator and network client.

    Translators are registered by scoring_type string -- this is the same
    string a blueprint sets as ``scoring.params.scoring_type`` (for link
    scoring) or ``expansion.llm_type`` (for topic expansion), and the same
    string used as the top-level key in ``keys.json`` to look up that
    provider's API key(s). To add a new LLM provider: implement a
    translator class with translate_request(context) and
    translate_response(response), then register it in the `translators`
    dict below.

    Args:
        key_manager: Supplies a rotating API key for the request's provider.
        client: Network client used to actually send the request. Defaults
            to a plain NetworkClient.
    """

    # Request URL per provider (Gemini: base URL, the model is appended).
    DEFAULT_ENDPOINTS = {
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
        "openai": "https://api.openai.com/v1/chat/completions",
        "anthropic": "https://api.anthropic.com/v1/messages",
        "gemini": GeminiTranslator.BASE_URL,
        "nvidia": "https://integrate.api.nvidia.com/v1/chat/completions",
        "groq": "https://api.groq.com/openai/v1/chat/completions",
    }

    translators = {
        "openrouter": OpenRouterTranslator,
        "openai": OpenAITranslator,
        "anthropic": AnthropicTranslator,
        "gemini": GeminiTranslator,
        "nvidia": NvidiaTranslator,
        "groq": GroqTranslator,
    }

    def __init__(
        self,
        key_manager: KeyManager,
        client: NetworkClient | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        endpoints: dict[str, str] | None = None,
    ):
        self.client = client or NetworkClient()
        self.key_manager = key_manager
        # Optional request parameters; None leaves the provider's default.
        self.max_tokens = max_tokens
        self.temperature = temperature
        # Only entries that differ from the built-in URL are applied.
        self.endpoints = {
            p: u for p, u in (endpoints or {}).items()
            if u and u != self.DEFAULT_ENDPOINTS.get(p)
        }

    def _apply_options(self, llm_type: str, params: dict) -> None:
        """Set the configured max_tokens/temperature in the provider's own
        request shape (Gemini nests them under generationConfig)."""
        data = params.get("data")
        if not isinstance(data, dict):
            return
        if llm_type == "gemini":
            cfg = data.setdefault("generationConfig", {})
            if self.max_tokens is not None:
                cfg["maxOutputTokens"] = self.max_tokens
            if self.temperature is not None:
                cfg["temperature"] = self.temperature
            return
        if self.max_tokens is not None:
            data["max_tokens"] = self.max_tokens
        if self.temperature is not None:
            data["temperature"] = self.temperature

    def _apply_endpoint(self, llm_type: str, params: dict, context) -> None:
        endpoint = self.endpoints.get(llm_type)
        if not endpoint:
            return
        if llm_type == "gemini":
            endpoint = f"{endpoint.rstrip('/')}/{context.get_model_information()}:generateContent"
        params["url"] = endpoint

    async def send(self, context) -> dict:
        """Send one LLM request end to end: key, translate, dispatch, normalize.

        Raises:
            ValueError: If `context`'s scoring type has no registered translator.
        """
        llm_type = context.get_scoring_type()

        translator_cls = self.translators.get(llm_type)
        if translator_cls is None:
            raise ValueError(
                f"Unknown scoring type: {llm_type!r}. "
                f"Registered: {list(self.translators.keys())}"
            )

        while True:
            key = await self.key_manager.next_key(llm_type)
            context.set_key(key)
            params = translator_cls.translate_request(context)
            self._apply_endpoint(llm_type, params, context)
            self._apply_options(llm_type, params)
            try:
                response = await self.client.emit_request(params)
                break
            except aiohttp.ClientResponseError as e:
                # A rejected key (401/403) will never start working: drop it
                # from rotation and retry with the next one, if any is left.
                if e.status in (401, 403) and await self.key_manager.mark_invalid(
                    llm_type, key
                ):
                    continue
                raise
        usage = getattr(translator_cls, "translate_usage", None)
        if usage is not None and hasattr(context, "set_usage"):
            context.set_usage(*usage(response))
        return translator_cls.translate_response(response)
