from typing import Optional


class LlmContext:
    """Immutable request object passed to LlmHandler.

    Carries all info needed to construct the LLM API call. Subclassed
    by ScoringContext and ExpansionContext for their respective roles.
    """

    def __init__(self, llm_type: str, model_information: str, prompt: str):
        self.llm_type = llm_type
        self.model_information = model_information
        self.prompt = prompt
        self.key: Optional[str] = None

    def get_llm_type(self) -> str:
        return self.llm_type

    def get_scoring_type(self) -> str:
        return self.get_llm_type()

    def get_key(self) -> Optional[str]:
        return self.key

    def set_key(self, key: str) -> None:
        self.key = key

    def get_model_information(self) -> str:
        return self.model_information

    def get_endpoint(self) -> str:
        return self.model_information

    def get_prompt(self) -> str:
        return self.prompt

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} type={self.get_llm_type()} "
            f"model={self.model_information!r}>"
        )
