"""Link-scoring policies. Each one is a ``RelevanceScorer`` (see
pipelines/contracts.py): it writes ``_nlp_score`` and ``nlp_vector`` on every
link. The benchmark ranks the frontier by ``_nlp_score`` alone (strategy
``passthrough``), so a policy is judged on its own scores, not on the
depth penalty and weights in priority/strategy.py.

Equal scores keep first-in-first-out order, so a constant score is BFS.
"""
import random

from .graph import BASE_URL, TOPIC_TERMS, FrozenGraph


class _Policy:
    def __init__(self, graph: FrozenGraph, seed: int):
        self.graph = graph
        self.rng = random.Random(f"policy:{seed}")
        self.terms = set(graph.terms or TOPIC_TERMS)

    def score(self, link, parent) -> float:
        raise NotImplementedError

    async def score_links(self, links, parent):
        for link in links:
            link._nlp_score = round(self.score(link, parent), 6)
            link.nlp_vector = {"target_similarity": link._nlp_score}
        return links

    async def update_space(self, links) -> None:
        pass


class Bfs(_Policy):
    def score(self, link, parent):
        return 0.0


class RandomOrder(_Policy):
    def score(self, link, parent):
        return self.rng.random()


class AnchorLexical(_Policy):
    """Share of the anchor's words that are topic words. Needs no model."""

    def score(self, link, parent):
        terms = self.terms
        words = link.anchor.lower().split()
        return sum(w in terms for w in words) / len(words) if words else 0.0


class Oracle(_Policy):
    """Knows the label of every target. A ceiling, not a contender."""

    def score(self, link, parent):
        name = link.url.rsplit("/", 1)[1]
        return 1.0 if self.graph.pages.get(name, {}).get("relevant") else 0.0


POLICIES = {"bfs": Bfs, "random": RandomOrder, "anchor_lexical": AnchorLexical, "oracle": Oracle}
assert BASE_URL  # policies see URLs under graph.BASE_URL
