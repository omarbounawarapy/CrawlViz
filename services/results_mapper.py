from typing import Any

from .llm_contracts import VALID_RELEVANCE_TYPES, Outcomes, ScoredLink, parse_scored_link


class ResultMapper:
    """Maps raw LLM scoring output back onto Link objects.

    Expected LLM output format::

        {
            "https://example.com/page": {
                "score": 85,
                "relevance_type": "direct",
                "expansions": ["sentence1", "sentence2"]
            },
            ...
        }
    """

    VALID_RELEVANCE_TYPES = VALID_RELEVANCE_TYPES

    def __init__(self) -> None:
        # scored, missing, malformed_entry, malformed_response
        self.outcomes = Outcomes()

    def map_results(self, results: dict[str, Any], links: list) -> list:
        """Apply LLM scoring results to `links` in place.

        Links not present in `results` receive safe defaults rather than
        being left unscored.

        Returns:
            The same `links` list, mutated.
        """
        if not results or not isinstance(results, dict):
            self.outcomes["malformed_response"] += 1
            return links

        for link in links:
            entry = results.get(link.url)
            if entry is None:
                # LLM didn't score this link -- set safe defaults.
                self.outcomes["missing"] += 1
                link.score = link.score or 0
                link.relevance_type = "irrelevant"
                link.expansions = []
                continue
            self._apply(link, entry)

        return links

    def map_partial(self, results: dict[str, Any], links: list) -> list:
        """Apply LLM scoring results only to links present in `results`.

        Links missing from `results` are left untouched.
        """
        if not results or not isinstance(results, dict):
            if results is not None and results != {}:
                self.outcomes["malformed_response"] += 1
            return links

        url_index = {link.url: link for link in links}

        for url, entry in results.items():
            link = url_index.get(url)
            if link is None:
                continue
            self._apply(link, entry)

        return links

    def _apply(self, link, entry: Any) -> None:
        parsed = parse_scored_link(entry)
        if parsed is None:
            self.outcomes["malformed_entry"] += 1
            link.score = link.score or 0
            link.relevance_type = "ambiguous"
            link.expansions = []
            return
        self.outcomes["scored"] += 1
        link.score = parsed.score
        link.relevance_type = parsed.relevance_type
        link.expansions = parsed.expansions

    # =========================================================
    # FIELD PARSERS
    # =========================================================

    def _parse_score(self, raw: Any) -> int:
        return ScoredLink(score=raw).score

    def _parse_relevance_type(self, raw: Any) -> str:
        return ScoredLink(relevance_type=raw).relevance_type

    def _parse_expansions(self, raw: Any) -> list[str]:
        return ScoredLink(expansions=raw).expansions
