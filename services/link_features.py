"""One link's NLP feature vector and composite score.

This is the cheap first stage of the scoring cascade: every discovered link
passes through it. ``NLPService.score_links`` builds one ``ParentContext``
per page and calls ``LinkFeatureScorer.score_link`` for each of its links.
See docs/adr/0003-nlp-service-split.md.
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from scipy.spatial.distance import cosine

from config import NLP_COMPOSITE_WEIGHTS
from models.link import Link
from nlp import BaseEmbeddingEngine, FeatureExtractor, VectorSpace
from traceability.nlp_trace_events import (
    NLP_FeaturesExtracted,
    NLP_InputReceived,
    NLP_ScoreEmitted,
    NLP_SimilarityScored,
    NLP_VectorComposed,
)
from traceability.trace_context import get_trace
from utils.html_utils import document_text

if TYPE_CHECKING:
    from traceability.emitter import TraceEmitter


# Navigation / legal page phrases; a link that embeds close to one of these is
# almost never topical content (see FeatureExtractor.boilerplate_score).
BOILERPLATE_PROTOTYPES = [
    "contact us", "privacy policy", "copyright", "disclaimers", "about us",
    "terms of use", "log in", "sign up", "main page", "site map", "current events",
    "recent changes", "random page", "donate", "help", "cookie policy",
]

# Density radius until the first space statistics are derived.
DEFAULT_DENSITY_RADIUS = 0.3
# Vocabulary words shorter than this carry little topic signal.
MIN_VOCAB_WORD_CHARS = 4
# Cluster centroids need at least this many vectors in the space.
MIN_VECTORS_FOR_CLUSTERS = 3
# DBSCAN's label for points outside every cluster.
NOISE_CLUSTER = -1
# Anchor and context previews in trace events are cut to these lengths.
ANCHOR_PREVIEW_CHARS = 80
CONTEXT_PREVIEW_CHARS = 120


@dataclass(frozen=True)
class FeatureSettings:
    """The NLP settings link features depend on (RuntimeConfig.nlp)."""

    target_top_k: int = 2
    # Feature name to weight in the composite score; None means the defaults.
    composite_weights: dict[str, float] | None = None
    cluster_eps: float = 0.3
    cluster_min_samples: int = 2


@dataclass(frozen=True)
class ParentContext:
    """What every link of one parent page is scored against."""

    content: str
    # The parent page's embedding, or the target vector when it has no text.
    vector: np.ndarray
    # Similarity of parent and target, floored at 0.
    relevance: float
    space: VectorSpace
    space_matrix: np.ndarray
    cluster_centroids: dict[int, np.ndarray]
    trace_id: str
    node_id: str


class LinkFeatureScorer:
    """Turns a link into its feature vector (``nlp_vector``) and composite
    score (``_nlp_score``), and keeps the per-space statistics the features
    need, recomputed only when the space version changes."""

    def __init__(
        self,
        engine: BaseEmbeddingEngine,
        settings: FeatureSettings,
        tracer: "TraceEmitter | None" = None,
    ) -> None:
        self.engine = engine
        self.settings = settings
        self.extractor = FeatureExtractor(target_top_k=settings.target_top_k)
        self._tracer = tracer
        self._boilerplate_matrix: np.ndarray | None = None
        self._vocab: set[str] = set()
        self._density_radius = DEFAULT_DENSITY_RADIUS
        self._stats_version: int | None = None

    async def _emit(self, event: object) -> None:
        if self._tracer is not None:
            await self._tracer.emit(event)

    async def parent_context(
        self, parent: object, space: VectorSpace, target_vec: np.ndarray, target_topic: str
    ) -> ParentContext:
        """Everything shared by the links of `parent`, computed once."""
        trace_id, node_id = get_trace()
        content = document_text(getattr(parent, "content", "") or "")
        vector = self.engine.encode(content) if content else target_vec
        space_matrix = space.get_matrix()
        self._refresh_space_stats(space, target_topic)
        relevance = float(max(0.0, 1.0 - cosine(vector, target_vec)))
        return ParentContext(
            content=content,
            vector=vector,
            relevance=relevance,
            space=space,
            space_matrix=space_matrix,
            cluster_centroids=self._cluster_centroids(space),
            trace_id=trace_id,
            node_id=node_id,
        )

    def _refresh_space_stats(self, space: VectorSpace, target_topic: str) -> None:
        """(Re)derive per-space statistics used by the feature extractor:
        boilerplate prototype matrix, target vocabulary, adaptive density radius.
        Cheap, and only recomputed when the space version changes."""
        if self._boilerplate_matrix is None:
            self._boilerplate_matrix = self.engine.encode(BOILERPLATE_PROTOTYPES)
        if self._stats_version == space.version:
            return
        texts = [target_topic] + [
            e.metadata.get("text", "") for e in space.entries if e.metadata.get("text")
        ]
        self._vocab = {
            t for text in texts for t in re.findall(r"\w+", text.lower())
            if len(t) >= MIN_VOCAB_WORD_CHARS
        }
        self._density_radius = self.extractor.adaptive_radius(space.get_matrix())
        self._stats_version = space.version

    def _cluster_centroids(self, space: VectorSpace) -> dict[int, np.ndarray]:
        if len(space) < MIN_VECTORS_FOR_CLUSTERS:
            return {}
        clusters = space.get_clusters(
            eps=self.settings.cluster_eps, min_samples=self.settings.cluster_min_samples
        )
        mat = space.get_matrix()
        centroids = {}
        for cluster_id, keys in clusters.items():
            if cluster_id == NOISE_CLUSTER:
                continue
            indices = [i for i, e in enumerate(space.entries) if e.key in keys]
            if indices:
                centroids[cluster_id] = np.mean(mat[indices], axis=0)
        return centroids

    async def score_link(self, link: Link, parent: ParentContext) -> None:
        """Set ``link.nlp_vector`` and ``link._nlp_score``."""
        await self._emit(NLP_InputReceived(
            trace_id=parent.trace_id,
            node_id=parent.node_id,
            link_url=link.url,
            anchor_preview=(link.anchor or "")[:ANCHOR_PREVIEW_CHARS],
            context_preview=(link.context or "")[:CONTEXT_PREVIEW_CHARS],
            parent_content_len=len(parent.content),
            space_size=len(parent.space),
        ))
        link.nlp_vector = await self.generate_vector(link, parent)
        link._nlp_score = await self.composite_score(
            link.nlp_vector, link_url=link.url, trace_id=parent.trace_id, node_id=parent.node_id
        )
        await self._emit(NLP_ScoreEmitted(
            trace_id=parent.trace_id,
            node_id=parent.node_id,
            link_url=link.url,
            nlp_score=link._nlp_score,
            space_version=parent.space.version,
        ))

    async def generate_vector(self, link: Link, parent: ParentContext) -> dict[str, float]:
        anchor_text = (link.anchor or "").strip()
        context_text = link.context or ""
        # Measured (tools/nlp_eval.py, AUC vs LLM labels, top_k=2): this
        # marker-tagged text beats anchor-only (0.607), anchor+context (0.604)
        # and slug variants (<=0.60), so keep it; the anchor is scored
        # separately as `anchor_similarity`.
        link_text = f"[URL]{link.url} [ANCHOR]{link.anchor} [CTX]{link.context}"

        anchor_vec = self.engine.encode(anchor_text) if anchor_text else None
        link_vec = self.engine.encode(link_text)
        context_vec = self.engine.encode(context_text) if context_text else link_vec
        link._embedding = link_vec

        features = self.extractor.extract_all(
            link_vec=link_vec,
            anchor=link.anchor or "",
            context_vec=context_vec,
            parent_vec=parent.vector,
            parent_content=parent.content,
            space_matrix=parent.space_matrix,
            vector_space=parent.space,
            cluster_centroids=parent.cluster_centroids,
            anchor_vec=anchor_vec,
            parent_relevance=parent.relevance,
            boilerplate_matrix=self._boilerplate_matrix,
            vocab=self._vocab,
            density_radius=self._density_radius,
        )
        if parent.trace_id:
            await self._emit_feature_traces(link, parent, features)
        return features

    async def _emit_feature_traces(
        self, link: Link, parent: ParentContext, features: dict[str, float]
    ) -> None:
        await self._emit(NLP_FeaturesExtracted(
            trace_id=parent.trace_id,
            node_id=parent.node_id,
            link_url=link.url,
            features=features,
            embedding_dim=self.engine.dim,
            space_size=len(parent.space),
            cluster_count=len(parent.cluster_centroids),
        ))
        await self._emit(NLP_SimilarityScored(
            trace_id=parent.trace_id,
            node_id=parent.node_id,
            link_url=link.url,
            target_similarity=features.get("target_similarity", 0.0),
            contextual_consistency=features.get("contextual_consistency", 0.0),
            novelty_injection=features.get("novelty_injection", 0.0),
            region_density=features.get("region_density", 0.0),
            cluster_distance=features.get("cluster_distance", 0.0),
            coverage_gap=features.get("coverage_gap", 0.0),
        ))

    async def composite_score(
        self,
        features: dict[str, float],
        link_url: str = "",
        trace_id: str = "",
        node_id: str = "",
    ) -> float:
        """The weighted sum of the features, clamped to [0, 1]."""
        if not features:
            return 0.0

        weights = self.settings.composite_weights or NLP_COMPOSITE_WEIGHTS

        contributions = {k: features.get(k, 0.0) * w for k, w in weights.items()}
        raw_sum = sum(contributions.values())
        score = float(max(0.0, min(1.0, raw_sum)))

        if trace_id:
            await self._emit(NLP_VectorComposed(
                trace_id=trace_id,
                node_id=node_id,
                link_url=link_url,
                weights_used=weights,
                weighted_contributions=contributions,
                raw_sum=raw_sum,
                final_score=score,
            ))

        return score
