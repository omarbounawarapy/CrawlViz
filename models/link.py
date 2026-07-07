import json

import numpy as np


class Link:
    """A single outgoing link extracted from a page, with its anchor text
    and surrounding context.

    `score`, `nlp_vector`, and `_embedding` start unset and are filled in
    by the NLP and scoring pipelines once this link has been evaluated;
    `relevance_type` and `expansions` are filled in from the LLM's
    response (see services/results_mapper.py).

    Args:
        url: The link's resolved target URL.
        anchor: The link's visible anchor text.
        context: Nearby page text used as scoring context.
    """

    def __init__(self, url: str, anchor: str, context: str):
        self.url = url
        self.anchor = anchor
        self.context = context

        # Filled in by nlp_service.py while scoring this link.
        self.score: int | None = None
        self.nlp_vector: dict = {}
        self._nlp_score: float = 0.0
        self._embedding: np.ndarray | None = None

        # Filled in by services/results_mapper.py from the LLM response.
        self.relevance_type: str | None = None
        self.expansions: list[str] = []

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "anchor": self.anchor,
            "context": self.context,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def get_url(self) -> str:
        return self.url
