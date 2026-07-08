from typing import Any


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

    VALID_RELEVANCE_TYPES = {"direct", "partial", "irrelevant", "ambiguous"}

    def map_results(self, results: dict[str, Any], links: list) -> list:
        """Apply LLM scoring results to `links` in place.

        Links not present in `results` receive safe defaults rather than
        being left unscored.

        Returns:
            The same `links` list, mutated.
        """
        if not results or not isinstance(results, dict):
            return links

        for link in links:
            entry = results.get(link.url)
            if entry is None:
                # LLM didn't score this link -- set safe defaults.
                link.score = link.score or 0
                link.relevance_type = "irrelevant"
                link.expansions = []
                continue

            link.score = self._parse_score(entry.get("score"))
            link.relevance_type = self._parse_relevance_type(entry.get("relevance_type"))
            link.expansions = self._parse_expansions(entry.get("expansions"))

        return links

    def map_partial(self, results: dict[str, Any], links: list) -> list:
        """Apply LLM scoring results only to links present in `results`.

        Links missing from `results` are left untouched.
        """
        if not results:
            return links

        url_index = {link.url: link for link in links}

        for url, entry in results.items():
            link = url_index.get(url)
            if link is None:
                continue
            link.score = self._parse_score(entry.get("score"))
            link.relevance_type = self._parse_relevance_type(entry.get("relevance_type"))
            link.expansions = self._parse_expansions(entry.get("expansions"))

        return links

    # =========================================================
    # FIELD PARSERS
    # =========================================================

    def _parse_score(self, raw: Any) -> int:
        try:
            val = int(raw)
            return max(0, min(100, val))
        except (TypeError, ValueError):
            return 0

    def _parse_relevance_type(self, raw: Any) -> str:
        if isinstance(raw, str) and raw.lower() in self.VALID_RELEVANCE_TYPES:
            return raw.lower()
        return "ambiguous"

    def _parse_expansions(self, raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        return [str(s).strip() for s in raw if isinstance(s, str) and s.strip()]
