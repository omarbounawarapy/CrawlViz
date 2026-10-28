import logging
import re
from typing import TYPE_CHECKING

import numpy as np
from scipy.spatial.distance import cosine

from config import NLP_COMPOSITE_WEIGHTS
from infrastructure import LlmHandler
from utils.html_utils import document_text
from nlp import (
    BaseEmbeddingEngine,
    BufferManager,
    FeatureExtractor,
    SpaceStore,
    VectorSpace,
    create_embedding_engine,
)
from .space_bootstrap import SpaceBootstrapper
from traceability.nlp_trace_events import (
    NLP_FeaturesExtracted,
    NLP_InputReceived,
    NLP_ScoreEmitted,
    NLP_SimilarityScored,
    NLP_VectorComposed,
)
from traceability.trace_context import get_trace

if TYPE_CHECKING:
    from traceability.emitter import TraceEmitter

logger = logging.getLogger(__name__)


# Navigation / legal page phrases; a link that embeds close to one of these is
# almost never topical content (see FeatureExtractor.boilerplate_score).
BOILERPLATE_PROTOTYPES = [
    "contact us", "privacy policy", "copyright", "disclaimers", "about us",
    "terms of use", "log in", "sign up", "main page", "site map", "current events",
    "recent changes", "random page", "donate", "help", "cookie policy",
]


class NLPService:
    """Core NLP subsystem.

    Responsibilities:
        - Manage the semantic vector space lifecycle (build / load / save).
        - Embed links, parent nodes, and target topics.
        - Compute per-link feature vectors (nlp_vector).
        - Provide space-level signals for the scoring pipeline.
        - Accept batch updates from the space updater (never real-time).

    The space is stable during a crawl session: link scoring only *reads*
    it. Growth happens out of band, via ``update_space()`` (called once
    per scored node from ``ScoringPipeline``) encoding each link's LLM
    expansions and forwarding them to the shared ``BufferManager``.
    ``SpaceUpdater`` (see ``nlp/space_updater.py``) periodically drains
    that buffer and commits the vectors into ``self.space``, so the space
    itself never mutates on the hot scoring path.

    If no ``buffer_manager`` is wired in (e.g. standalone/test usage),
    ``update_space()`` falls back to an internal buffer that a caller can
    flush explicitly with ``flush_buffer()``.

    Args:
        blueprint_id: Identifies this blueprint's persisted semantic space.
        target_topic: The crawl's target topic; anchors the space's target vector.
        llm_handler: Used to generate the target topic's semantic expansions
            (see ``SpaceBootstrapper``).
        expansion_config: The blueprint's ``expansion`` sub-dict (llm_type,
            llm_model, style, num_descriptions, ...).
        engine: A ready embedding engine; overrides ``embedding_backend``.
        embedding_backend: Name registered with `nlp.create_embedding_engine`.
        model_name: Passed through to the embedding backend.
        store_base_dir: Root directory for persisted spaces; a space is keyed
            by (blueprint_id, model_name).
        persist_space: When False (default) the stored space is read-only after
            its first bootstrap, so every run starts from the same state. When
            True, the run writes its growth back.
        tracer: Optional TraceEmitter; when None, tracing is a no-op.
        buffer_manager: The live crawl's BufferManager (drained by
            SpaceUpdater). When provided, ``update_space()`` forwards
            encoded expansions there instead of buffering locally.
    """

    def __init__(
        self,
        blueprint_id: str,
        target_topic: str,
        llm_handler: LlmHandler,
        expansion_config: dict,
        embedding_backend: str = "sentence_transformers",
        model_name: str = "all-MiniLM-L6-v2",
        store_base_dir: str = ".space_store",
        persist_space: bool = False,
        tracer: "TraceEmitter | None" = None,
        buffer_manager: "BufferManager | None" = None,
        engine: BaseEmbeddingEngine | None = None,
        composite_weights: dict[str, float] | None = None,
        target_top_k: int = 2,
        cluster_eps: float = 0.3,
        cluster_min_samples: int = 2,
    ):
        self.composite_weights = composite_weights
        self.cluster_eps = cluster_eps
        self.cluster_min_samples = cluster_min_samples
        self.blueprint_id = blueprint_id
        self.target_topic = target_topic

        self.engine: BaseEmbeddingEngine = engine or create_embedding_engine(
            backend=embedding_backend,
            model_name=model_name,
        )

        self.store = SpaceStore(base_dir=store_base_dir, model_name=model_name)
        self.extractor = FeatureExtractor(target_top_k=target_top_k)
        self.bootstrapper = SpaceBootstrapper(
            blueprint_id, self.engine, llm_handler, expansion_config, tracer=tracer
        )
        self.space: VectorSpace | None = None
        self.persist_space = persist_space
        # Version of the stored space this run began from (see start()).
        self.start_version: int | None = None
        self.target_vec: np.ndarray | None = None
        self.buffer_manager = buffer_manager
        # Local fallback buffer, only used when no buffer_manager is wired in.
        self._buffer: list[tuple[str, np.ndarray, dict]] = []
        self._tracer = tracer
        # Derived once per space version / at start(): see _refresh_space_stats().
        self._boilerplate_matrix: np.ndarray | None = None
        self._vocab: set[str] = set()
        self._density_radius: float = 0.3
        self._stats_version: int | None = None

    async def _emit(self, event) -> None:
        """Forward `event` to the attached tracer, if any; a no-op otherwise."""
        if self._tracer is not None:
            await self._tracer.emit(event)

    # =========================================================
    # LIFECYCLE
    # =========================================================

    async def start(self) -> None:
        if self.store.exists(self.blueprint_id):
            self.load_space()
        else:
            await self.build_space()
        self.start_version = self.space.version
        logger.info(
            "Run starts from space v%s (%d vectors), persist_space=%s",
            self.start_version, len(self.space), self.persist_space,
        )

    async def build_space(self) -> None:
        """Bootstrap the space from the target topic (see SpaceBootstrapper)."""
        await self.bootstrapper.build(self.target_topic, adopt=self._adopt_space)

    def _adopt_space(self, space: VectorSpace, target_vec: np.ndarray) -> None:
        self.space, self.target_vec = space, target_vec
        self.save_space()

    def load_space(self) -> None:
        path = self.store.space_path(self.blueprint_id)
        self.space = VectorSpace(dim=self.engine.dim)
        self.space.load(path)
        if self.space.dim != self.engine.dim:
            raise ValueError(
                f"Stored space has dim {self.space.dim} but the embedding engine "
                f"produces dim {self.engine.dim}; the space was built with a "
                f"different model. Rebuild it or key it by model."
            )
        self.target_vec = self.engine.encode(self.target_topic)
        logger.info("Loaded existing space: %s", self.space)

    def _refresh_space_stats(self) -> None:
        """(Re)derive per-space statistics used by the feature extractor:
        boilerplate prototype matrix, target vocabulary, adaptive density radius.
        Cheap, and only recomputed when the space version changes."""
        if self._boilerplate_matrix is None:
            self._boilerplate_matrix = self.engine.encode(BOILERPLATE_PROTOTYPES)
        if self.space is None or self._stats_version == self.space.version:
            return
        texts = [self.target_topic] + [
            e.metadata.get("text", "") for e in self.space.entries if e.metadata.get("text")
        ]
        self._vocab = {
            t for text in texts for t in re.findall(r"\w+", text.lower()) if len(t) > 3
        }
        self._density_radius = self.extractor.adaptive_radius(self.space.get_matrix())
        self._stats_version = self.space.version

    def save_space(self) -> None:
        if self.space is None:
            return
        if not self.persist_space and self.store.exists(self.blueprint_id):
            return
        path = self.store.space_path(self.blueprint_id)
        self.space.save(path)
        self.store.record_save(
            self.blueprint_id,
            n_vectors=len(self.space),
            version=self.space.version,
        )
        logger.info("Space saved to %s", path)

    # =========================================================
    # LINK SCORING (MAIN PIPELINE HOOK)
    # =========================================================

    async def score_links(self, links: list, parent) -> list:
        """Compute NLP feature vectors and a composite score for each link.

        Raises:
            RuntimeError: If called before `start()` has built or loaded a space.
        """
        if self.space is None:
            raise RuntimeError("NLPService.start() must be called before score_links()")

        trace_id, node_id = get_trace()

        parent_content = document_text(getattr(parent, "content", "") or "")
        parent_vec = self.engine.encode(parent_content) if parent_content else self.target_vec
        space_matrix = self.space.get_matrix()
        self._refresh_space_stats()
        parent_relevance = float(max(0.0, 1.0 - cosine(parent_vec, self.target_vec)))

        cluster_centroids = await self._get_cluster_centroids()

        for link in links:
            try:
                await self._emit(NLP_InputReceived(
                    trace_id=trace_id,
                    node_id=node_id,
                    link_url=link.url,
                    anchor_preview=(link.anchor or "")[:80],
                    context_preview=(link.context or "")[:120],
                    parent_content_len=len(parent_content),
                    space_size=len(self.space),
                ))

                link.nlp_vector = await self.generate_vector(
                    link,
                    parent_vec,
                    parent_content,
                    space_matrix,
                    cluster_centroids,
                    parent_relevance=parent_relevance,
                    trace_id=trace_id,
                    node_id=node_id,
                )

                link._nlp_score = await self._composite_score(
                    link.nlp_vector,
                    link_url=link.url,
                    trace_id=trace_id,
                    node_id=node_id,
                )

                await self._emit(NLP_ScoreEmitted(
                    trace_id=trace_id,
                    node_id=node_id,
                    link_url=link.url,
                    nlp_score=link._nlp_score,
                    space_version=self.space.version,
                ))

            except Exception:
                logger.exception("Failed to vectorize link: %s", link.url)
                link.nlp_vector = {}
                link._nlp_score = 0.0

        return links

    # =========================================================
    # VECTOR GENERATION (PER LINK)
    # =========================================================

    async def generate_vector(
        self,
        link,
        parent_vec: np.ndarray,
        parent_content: str,
        space_matrix: np.ndarray,
        cluster_centroids: dict[int, np.ndarray],
        parent_relevance: float = 0.0,
        trace_id: str = "",
        node_id: str = "",
    ) -> dict[str, float]:
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
            parent_vec=parent_vec,
            parent_content=parent_content,
            space_matrix=space_matrix,
            vector_space=self.get_space(),
            cluster_centroids=cluster_centroids,
            anchor_vec=anchor_vec,
            parent_relevance=parent_relevance,
            boilerplate_matrix=self._boilerplate_matrix,
            vocab=self._vocab,
            density_radius=self._density_radius,
        )
        if trace_id:
            await self._emit(NLP_FeaturesExtracted(
                trace_id=trace_id,
                node_id=node_id,
                link_url=link.url,
                features=features,
                embedding_dim=self.engine.dim,
                space_size=len(self.space),
                cluster_count=len(cluster_centroids),
            ))

            await self._emit(NLP_SimilarityScored(
                trace_id=trace_id,
                node_id=node_id,
                link_url=link.url,
                target_similarity=features.get("target_similarity", 0.0),
                contextual_consistency=features.get("contextual_consistency", 0.0),
                novelty_injection=features.get("novelty_injection", 0.0),
                region_density=features.get("region_density", 0.0),
                cluster_distance=features.get("cluster_distance", 0.0),
                coverage_gap=features.get("coverage_gap", 0.0),
            ))

        return features

    # =========================================================
    # SPACE UPDATES (BATCH ONLY -- SPACE REMAINS STABLE UNTIL FLUSH)
    # =========================================================

    async def update_space(self, scoring_results: list) -> None:
        """Encode each scored link's LLM expansions and forward them for
        eventual inclusion in the semantic space.

        Called once per scored node from ``ScoringPipeline`` right after
        the LLM scoring call returns. When a ``buffer_manager`` was wired
        in at construction (the live crawl path), vectors go there and
        ``SpaceUpdater`` commits them on its own schedule. Otherwise they
        accumulate in a local buffer that must be flushed explicitly via
        ``flush_buffer()``.
        """
        items: list[tuple[str, np.ndarray, dict]] = []
        for link in scoring_results:
            expansions = getattr(link, "expansions", []) or []
            for i, sentence in enumerate(expansions):
                vec = self.engine.encode(sentence)
                items.append((
                    f"{link.url}::exp::{i}",
                    vec,
                    {"type": "expansion", "source_url": link.url, "text": sentence},
                ))

        if not items:
            return

        if self.buffer_manager is not None:
            await self.buffer_manager.add_batch(items)
            logger.debug("Forwarded %d expansion vectors to buffer manager", len(items))
        else:
            self._buffer.extend(items)
            logger.debug("Buffer has %d pending vectors (local fallback)", len(self._buffer))

    def flush_buffer(self) -> None:
        """Flush the local fallback buffer directly into the space.

        Only relevant when this NLPService was constructed without a
        ``buffer_manager`` (e.g. standalone/test usage) -- in the live
        crawl path, SpaceUpdater drains buffer_manager instead and this
        local buffer stays empty.
        """
        if not self._buffer:
            return
        self.space.add_batch(self._buffer)
        logger.info(
            "Flushed %d vectors to space (space size now %d)",
            len(self._buffer), len(self.space),
        )
        self._buffer.clear()
        self.save_space()

    # =========================================================
    # INTERNAL HELPERS
    # =========================================================

    async def _get_cluster_centroids(self) -> dict[int, np.ndarray]:
        if self.space is None or len(self.space) < 3:
            return {}
        clusters = self.space.get_clusters(
            eps=self.cluster_eps, min_samples=self.cluster_min_samples
        )
        mat = self.space.get_matrix()
        centroids = {}
        for cluster_id, keys in clusters.items():
            if cluster_id == -1:
                continue
            indices = [
                i for i, e in enumerate(self.space.entries) if e.key in keys
            ]
            if indices:
                cluster_vecs = mat[indices]
                centroids[cluster_id] = np.mean(cluster_vecs, axis=0)
        return centroids

    async def _composite_score(
        self,
        features: dict[str, float],
        link_url: str = "",
        trace_id: str = "",
        node_id: str = "",
    ) -> float:
        if not features:
            return 0.0

        weights = self.composite_weights or NLP_COMPOSITE_WEIGHTS

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

    # =========================================================
    # PUBLIC ACCESSORS
    # =========================================================

    def get_space(self) -> VectorSpace | None:
        return self.space

    def get_target_vec(self) -> np.ndarray | None:
        return self.target_vec

    def buffer_size(self) -> int:
        return len(self._buffer)

    def space_size(self) -> int:
        return len(self.space) if self.space else 0
