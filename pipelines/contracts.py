"""Structural contracts for the collaborators the pipelines are given.

These describe what is consumed today, nothing more. Implementations
(NLPService, ScoringService, NetworkClient, TracedNetworkClient, and test
doubles) satisfy them by shape, without inheriting.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RelevanceScorer(Protocol):
    """Cheap similarity stage (NLPService).

    ``score_links`` writes ``_nlp_score`` and ``nlp_vector`` on every link
    and returns the links. ``update_space`` feeds scored links back into
    the semantic space.
    """

    async def score_links(self, links: list, parent: Any) -> list: ...

    async def update_space(self, links: list) -> None: ...


@runtime_checkable
class Annotator(Protocol):
    """Expensive LLM stage (ScoringService).

    ``score_links`` writes ``score``, ``relevance_type`` and ``expansions``
    on the links it annotates and returns them.
    """

    async def score_links(self, node: Any, links: list) -> list: ...


@runtime_checkable
class Fetcher(Protocol):
    """HTTP transport (NetworkClient, TracedNetworkClient).

    ``emit_request`` takes ``{"url", "headers", "data", "method"}`` and
    returns the response body as text; ``close`` releases the session.
    """

    async def emit_request(self, params: dict) -> str: ...

    async def close(self) -> None: ...
