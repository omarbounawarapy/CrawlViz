from typing import List

from models import Node, PromptBuilder, ScoringContext

from .results_mapper import ResultMapper


class ScoringService:
    """Builds an LLM scoring prompt for a batch of links and maps the
    response back onto them. The NLP pre-filtering that decides *which*
    links reach here lives in pipelines/scoring_pipeline.py.
    """

    def __init__(self, llm_handler, target_topic, strategy, scoring_type, model_information):
        self.handler = llm_handler
        self.prompt_builder = PromptBuilder(target_topic, strategy)
        self.results_mapper = ResultMapper()
        self.scoring_type = scoring_type
        self.model_information = model_information

    async def score_links(self, parent: Node, links) -> List:
        context = self.create_scoring_context(links)
        results = await self.handler.send(context)
        return self.results_mapper.map_results(results, links)

    def create_scoring_context(self, links) -> ScoringContext:
        prompt = self.prompt_builder.build_prompt(links)
        return ScoringContext(self.scoring_type, self.model_information, prompt)
