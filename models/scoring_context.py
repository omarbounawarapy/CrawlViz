from .llm_context import LlmContext
class ScoringContext(LlmContext):
    def get_scoring_type(self) -> str:
        return super().get_llm_type()
