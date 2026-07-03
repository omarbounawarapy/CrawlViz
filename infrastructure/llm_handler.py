from .open_router_translator import OpenRouterTranslator
from .network_client import NetworkClient
from .key_manager import KeyManager

class LlmHandler:
    """
    Routes LLM requests through the correct translator and network client.

    Translators are registered by scoring_type string.
    To add a new LLM provider: implement a translator class with
    translate_request(context) and translate_response(response),
    then register it in the `translators` dict.
    """

    translators = {
        "openrouter": OpenRouterTranslator,
    }

    def __init__(self,key_manager:KeyManager, client: NetworkClient = None,):
        self.client = client or NetworkClient()
        self.key_manager = key_manager

    async def send(self, context) -> dict:
        llm_type = context.get_scoring_type()
        key = await self.key_manager.next_key(llm_type)
        context.set_key(key)

        translator_cls = self.translators.get(llm_type)
        if translator_cls is None:
            raise ValueError(
                f"[LlmHandler] Unknown scoring type: {llm_type!r}. "
                f"Registered: {list(self.translators.keys())}"
            )

        params = translator_cls.translate_request(context)
        response = await self.client.emit_request(params)
        normalized = translator_cls.translate_response(response)
        return normalized

