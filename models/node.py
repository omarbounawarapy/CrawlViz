import logging
from asyncio import Future
from typing import Any

import numpy as np

from utils import build_url

from .domain import Domain
from .link import Link

logger = logging.getLogger(__name__)


class Node:
    """A single page in the crawl graph.

    Seed nodes (no parent) get their Domain injected directly and
    synthesize their own Link from the given url. Child nodes inherit
    their domain from the parent and carry the Link that discovered
    them (its anchor text and surrounding context feed the NLP/LLM
    scoring signals -- see nlp/feature_extractor.py).

    Args:
        node_id: This node's identifier, unique within one crawl's Storage.
        link: The Link that discovered this node. Required for child nodes;
            ignored for seed nodes, which synthesize their own from `url`.
        url: Seed URL. Only used when `parent` is None.
        domain: This node's Domain. Only used when `parent` is None; child
            nodes inherit their domain from `parent`.
        parent: The Node this one was discovered from, or None for a seed.
        llm_score: Relevance score assigned by the scoring pipeline, if any.
        priority: Initial crawl priority; refined as scoring/priority events arrive.
    """

    def __init__(
        self,
        node_id: int,
        link: Link | None = None,
        url: str | None = None,
        domain: Domain | None = None,
        parent: "Node | None" = None,
        llm_score: int | None = None,
        priority: float = 0.01,
    ):
        self.id = node_id
        self.link = link
        self.llm_score = llm_score
        self.priority = priority

        self.ready: Future = Future()

        self.parent = parent
        self.items: dict[str, Any] = {}
        self.links: list[Link] = []
        self.content: str = ""

        # NLP embedding (set by NLPService after content fetch)
        self._embedding: np.ndarray | None = None

        # Graph depth
        self.depth = 0 if parent is None else parent.get_depth() + 1

        # Domain resolution: seed nodes get their domain injected directly;
        # child nodes inherit it from their parent.
        if parent is None:
            self.domain = domain
            self.link = Link(url=url, anchor="", context="")
        else:
            if link is None:
                logger.error("Node %s has a parent but no link (invariant violation)", node_id)
            self.link = link
            self.domain = parent.get_domain()

    # =========================================================
    # COMPARISON (PRIORITY QUEUE)
    # =========================================================
    def __lt__(self, other: "Node") -> bool:
        if not isinstance(other, Node):
            # Lets this participate correctly in heapq/PriorityQueue
            # comparisons against non-Node sentinels (e.g. BasePipeline's
            # shutdown sentinel) instead of crashing with an AttributeError
            # on `other.priority` -- Python falls back to the other side's
            # reflected comparison instead.
            return NotImplemented
        return self.priority < other.priority

    # =========================================================
    # DOMAIN API
    # =========================================================
    def get_domain(self) -> Domain:
        return self.domain

    def get_domain_name(self) -> str:
        return self.domain.get_name()

    def get_domain_base_url(self) -> str:
        return self.domain.get_base_url()

    # =========================================================
    # CRAWLER POLICY
    # =========================================================
    def get_link_selector(self) -> str:
        return self.domain.get_link_selector()

    # =========================================================
    # IDENTITY
    # =========================================================
    def get_id(self) -> int:
        return self.id

    # =========================================================
    # GRAPH INFO
    # =========================================================
    def get_depth(self) -> int:
        return self.depth

    def get_parent(self) -> "Node | None":
        return self.parent

    # =========================================================
    # CONTENT & EXTRACTION
    # =========================================================
    def set_content(self, content: str) -> None:
        self.content = content

    def set_items(self, items: dict[str, Any]) -> None:
        self.items = items

    def add_item(self, item: Any, item_hash: str) -> None:
        self.items[item_hash] = item

    def set_links(self, links: list[Link]) -> None:
        self.links = links

    def get_items(self) -> dict[str, Any]:
        return self.items

    def get_links(self) -> list[Link]:
        return self.links

    def get_content(self) -> str:
        return self.content

    # =========================================================
    # SCORING STATE
    # =========================================================
    def set_llm_score(self, score: int) -> None:
        self.llm_score = score

    def get_llm_score(self) -> int:
        return self.llm_score

    def get_priority(self) -> int:
        return self.priority

    def decrease_priority(self, value: int) -> None:
        self.priority -= value

    # =========================================================
    # NLP EMBEDDING
    # =========================================================
    def set_embedding(self, vec: np.ndarray) -> None:
        self._embedding = vec

    def get_embedding(self) -> np.ndarray | None:
        return self._embedding

    def has_embedding(self) -> bool:
        return self._embedding is not None

    # =========================================================
    # URL HANDLING
    # =========================================================
    def get_link(self) -> str:
        return self.link.url

    def get_url(self) -> str:
        return self.link.url if hasattr(self.link, "url") else str(self.link)

    def get_full_url(self) -> str:
        return build_url(self.get_domain_base_url(), self.link.url)

    # =========================================================
    # ASYNC READINESS
    # =========================================================
    def update_state(self) -> None:
        if not self.ready.done():
            self.ready.set_result(True)

    # =========================================================
    # DEBUG
    # =========================================================
    def __repr__(self) -> str:
        return (
            f"<Node id={self.id} url={self.get_url()!r} "
            f"depth={self.depth} priority={self.priority}>"
        )

    def __str__(self) -> str:
        return self.__repr__()
