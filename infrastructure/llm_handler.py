from .anthropic_translator import AnthropicTranslator
from .gemini_translator import GeminiTranslator
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

    translators = {
        "openrouter": OpenRouterTranslator,
        "openai": OpenAITranslator,
        "anthropic": AnthropicTranslator,
        "gemini": GeminiTranslator,
        "nvidia": NvidiaTranslator,
    }

    def __init__(self, key_manager: KeyManager, client: NetworkClient | None = None):
        self.client = client or NetworkClient()
        self.key_manager = key_manager

    async def send(self, context) -> dict:
        """Send one LLM request end to end: key, translate, dispatch, normalize.

        Raises:
            ValueError: If `context`'s scoring type has no registered translator.
        """
        llm_type = context.get_scoring_type()
        key = await self.key_manager.next_key(llm_type)
        context.set_key(key)

        translator_cls = self.translators.get(llm_type)
        if translator_cls is None:
            raise ValueError(
                f"Unknown scoring type: {llm_type!r}. "
                f"Registered: {list(self.translators.keys())}"
            )

        params = translator_cls.translate_request(context)
        response = await self.client.emit_request(params)
        normalized = translator_cls.translate_response(response)
        return normalized
