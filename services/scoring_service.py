from models import Link, Node, PromptBuilder, ScoringContext

from .results_mapper import ResultMapper


class ScoringService:
    """Builds an LLM scoring prompt for a batch of links and maps the
    response back onto them. The NLP pre-filtering that decides *which*
    links reach here lives in pipelines/scoring_pipeline.py.

    Args:
        llm_handler: Client used to actually send the scoring request.
        target_topic: The crawl's target topic, restated in every prompt.
        strategy: Scoring strategy key from `models.prompts.STRATEGIES`.
        scoring_type: LLM provider key (e.g. "openrouter").
        model_information: Provider-specific model identifier.
    """

    def __init__(
        self,
        llm_handler,
        target_topic: str,
        strategy: str,
        scoring_type: str,
        model_information: str,
    ):
        self.handler = llm_handler
        self.prompt_builder = PromptBuilder(target_topic, strategy)
        self.results_mapper = ResultMapper()
        self.scoring_type = scoring_type
        self.model_information = model_information

    async def score_links(self, parent: Node, links: list[Link]) -> list[Link]:
        context = self.create_scoring_context(links)
        results = await self.handler.send(context)
        return self.results_mapper.map_results(results, links)

    def create_scoring_context(self, links: list[Link]) -> ScoringContext:
        prompt = self.prompt_builder.build_prompt(links)
        return ScoringContext(self.scoring_type, self.model_information, prompt)
