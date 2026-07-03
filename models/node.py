import logging
from asyncio import Future
from typing import Optional, Dict, List
import numpy as np
from .link import Link

logger = logging.getLogger(__name__)


class Node:
    """A single page in the crawl graph.

    Seed nodes (no parent) get their Domain injected directly and
    synthesize their own Link from the given url. Child nodes inherit
    their domain from the parent and carry the Link that discovered
    them (its anchor text and surrounding context feed the NLP/LLM
    scoring signals -- see nlp/feature_extractor.py).
    """

    def __init__(
        self,
        id: int,
        link=None,
        url=None,
        domain=None,
        parent=None,
        llm_score=None,
        priority: float = 0.01,
    ):
        self.id = id
        self.link = link
        self.llm_score = llm_score
        self.priority = priority

        self.ready: Future = Future()

        self.parent = parent
        self.items: Dict = {}
        self.links: List = []
        self.content: str = ""

        # NLP embedding (set by NLPService after content fetch)
        self._embedding: Optional[np.ndarray] = None

        # ── Graph depth ───────────────────────────────────────────
        self.depth = 0 if parent is None else parent.get_depth() + 1

        # ── Domain resolution ─────────────────────────────────────
        # Seed nodes get domain injected directly.
        # Child nodes inherit from parent.
        if parent is None:
            self.domain = domain
            self.link = Link(url=url,anchor="",context="")
        else:
            if link is None:
                logger.error("Node %s has a parent but no link (invariant violation)", id)
            self.link = link
            self.domain = parent.get_domain()

    # ── Comparison (priority queue) ───────────────────────────────
    def __lt__(self, other: "Node") -> bool:
        return self.priority < other.priority

    # ── Domain API ───────────────────────────────────────────────
    def get_domain(self):
        return self.domain

    def get_domain_name(self) -> str:
        return self.domain.get_name()

    def get_domain_base_url(self) -> str:
        return self.domain.get_base_url()

    def get_domain_scoring_type(self) -> str:
        return self.domain.get_scoring_type()

    def get_domain_model_information(self) -> str:
        return self.domain.get_model_information()

    def get_domain_scoring_prompt(self) -> str:
        return self.domain.get_scoring_prompt()

    # ── Crawler policy ───────────────────────────────────────────
    def get_link_selector(self):
        return self.domain.get_link_selector()

    def get_extraction_blueprint(self):
        return self.domain.get_extraction_blueprint()

    # ── Scoring policy ───────────────────────────────────────────
    def get_scoring_type(self) -> str:
        return self.domain.get_scoring_type()

    def get_scoring_model(self) -> str:
        return self.domain.get_scoring_model()

    def get_scoring_prompt(self) -> str:
        return self.domain.get_scoring_prompt()

    def get_scoring_config(self):
        return self.domain.get_scoring_config()

    # ── Identity ─────────────────────────────────────────────────
    def get_id(self) -> int:
        return self.id

    # ── Graph info ───────────────────────────────────────────────
    def get_depth(self) -> int:
        return self.depth

    def get_parent(self) -> Optional["Node"]:
        return self.parent

    # ── Content & extraction ─────────────────────────────────────
    def set_content(self, content: str) -> None:
        self.content = content

    def set_items(self, items: Dict) -> None:
        self.items = items

    def add_item(self, item, hash) -> None:
        self.items[hash] = item

    def set_links(self, links: List) -> None:
        self.links = links

    def get_items(self) -> Dict:
        return self.items

    def get_links(self) -> List:
        return self.links

    def get_content(self) -> str:
        return self.content

    # ── Scoring state ────────────────────────────────────────────
    def set_llm_score(self, score: int) -> None:
        self.llm_score = score

    def get_llm_score(self) -> int:
        return self.llm_score

    def get_priority(self) -> int:
        return self.priority

    def decrease_priority(self, value: int) -> None:
        self.priority -= value

    # ── NLP embedding ────────────────────────────────────────────
    def set_embedding(self, vec: np.ndarray) -> None:
        self._embedding = vec

    def get_embedding(self) -> Optional[np.ndarray]:
        return self._embedding

    def has_embedding(self) -> bool:
        return self._embedding is not None

    # ── URL handling ─────────────────────────────────────────────
    def get_link(self):
        return self.link.url

    def get_url(self) -> str:
        return self.link.url if hasattr(self.link, 'url') else str(self.link)

    def get_full_url(self) -> str:
        from utils import build_url
        return build_url(self.get_domain_base_url(), self.link.url)

    # ── Async readiness ──────────────────────────────────────────
    def update_state(self) -> None:
        if not self.ready.done():
            self.ready.set_result(True)

    # ── Debug ────────────────────────────────────────────────────
    def __repr__(self) -> str:
        return (
            f"<Node id={self.id} url={self.get_url()!r} "
            f"depth={self.depth} priority={self.priority}>"
        )

    def __str__(self) -> str:
        return self.__repr__()