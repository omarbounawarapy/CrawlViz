import os

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
        prefix = self.common_url_prefix(links)
        context = self.create_scoring_context(links, prefix)
        results = await self.handler.send(context)
        return self.results_mapper.map_results(self._restore_urls(results, prefix), links)

    @staticmethod
    def common_url_prefix(links: list[Link]) -> str:
        """Longest shared leading path (ending at a "/") of every link's URL.

        Only used to shorten the prompt; returns "" for fewer than two links.
        """
        if len(links) < 2:
            return ""
        prefix = os.path.commonprefix([link.url for link in links])
        return prefix[: prefix.rfind("/") + 1]

    @staticmethod
    def _normalize_results(results):
        """Coerce the LLM's answer to the ``{url: entry}`` shape ResultMapper expects.

        The prompt's OUTPUT FORMAT asks for ``{"results": [{"url": ..., "score": ...}]}``,
        so a list under "results" is the normal case. A ``{"results": {url: entry}}``
        dict or an already-flat ``{url: entry}`` dict are passed through.
        """
        if isinstance(results, dict) and "results" in results and len(results) == 1:
            results = results["results"]
        if isinstance(results, list):
            return {
                e["url"]: e for e in results if isinstance(e, dict) and "url" in e
            }
        return results

    @staticmethod
    def _restore_urls(results, prefix: str):
        """Re-attach `prefix` to result keys the LLM echoed back shortened.

        Keys that already start with the prefix (or a scheme) are left as is.
        """
        results = ScoringService._normalize_results(results)
        if not prefix or not isinstance(results, dict):
            return results
        return {
            (k if k.startswith(("http://", "https://")) else prefix + k): v
            for k, v in results.items()
        }

    def create_scoring_context(self, links: list[Link], url_prefix: str = "") -> ScoringContext:
        prompt = self.prompt_builder.build_prompt(links, url_prefix)
        return ScoringContext(self.scoring_type, self.model_information, prompt)
