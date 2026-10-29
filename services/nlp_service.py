import logging
from typing import TYPE_CHECKING

import numpy as np

from infrastructure import LlmHandler
from nlp import (
    BaseEmbeddingEngine,
    BufferManager,
    SpaceStore,
    VectorSpace,
    create_embedding_engine,
)
from .link_features import FeatureSettings, LinkFeatureScorer
from .space_bootstrap import SpaceBootstrapper

if TYPE_CHECKING:
    from traceability.emitter import TraceEmitter

logger = logging.getLogger(__name__)


class NLPService:
    """Core NLP subsystem.

    Responsibilities:
        - Own the semantic vector space: load, save, and buffered growth.
        - Score links against it (per-link work in ``LinkFeatureScorer``,
          services/link_features.py).
        - Build a blueprint's first space (``SpaceBootstrapper``,
          services/space_bootstrap.py).
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
        self.blueprint_id = blueprint_id
        self.target_topic = target_topic

        self.engine: BaseEmbeddingEngine = engine or create_embedding_engine(
            backend=embedding_backend,
            model_name=model_name,
        )

        self.store = SpaceStore(base_dir=store_base_dir, model_name=model_name)
        self.features = LinkFeatureScorer(
            self.engine,
            FeatureSettings(target_top_k, composite_weights, cluster_eps, cluster_min_samples),
            tracer=tracer,
        )
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
            self.start_version,
            len(self.space),
            self.persist_space,
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
        """Compute NLP feature vectors and a composite score for each link
        (see LinkFeatureScorer). A link that fails gets an empty vector and
        a score of 0.0, and the rest of the page is still scored.

        Raises:
            RuntimeError: If called before `start()` has built or loaded a space.
        """
        if self.space is None:
            raise RuntimeError("NLPService.start() must be called before score_links()")

        context = await self.features.parent_context(
            parent, self.space, self.target_vec, self.target_topic
        )
        for link in links:
            try:
                await self.features.score_link(link, context)
            except Exception:
                logger.exception("Failed to vectorize link: %s", link.url)
                link.nlp_vector = {}
                link._nlp_score = 0.0

        return links

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
                items.append(
                    (
                        f"{link.url}::exp::{i}",
                        vec,
                        {"type": "expansion", "source_url": link.url, "text": sentence},
                    )
                )

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
            len(self._buffer),
            len(self.space),
        )
        self._buffer.clear()
        self.save_space()

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
