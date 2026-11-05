"""Request URL per LLM provider. The keys are the provider names a blueprint sets."""

# Gemini: base URL, the model is appended.
_DEFAULT_ENDPOINTS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
    "nvidia": "https://integrate.api.nvidia.com/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
}


def default_llm_endpoints() -> dict[str, str]:
    """A fresh copy, so callers can adjust theirs."""
    return dict(_DEFAULT_ENDPOINTS)
