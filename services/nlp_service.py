import logging
import time
import numpy as np
from typing import List, Dict, Optional, Tuple

from infrastructure import LlmHandler
from nlp import (
    BaseEmbeddingEngine,
    ExpansionPromptBuilder,
    FeatureExtractor,
    SpaceStore,
    VectorSpace,
    create_embedding_engine,
)
from models import ExpansionContext

from traceability.trace_context import get_trace, new_trace_id
from traceability.nlp_trace_events import (
    NLP_InputReceived,
    NLP_FeaturesExtracted,
    NLP_SimilarityScored,
    NLP_VectorComposed,
    NLP_ScoreEmitted,
)
from traceability.expansion_trace_events import (
    EXP_Triggered,
    EXP_PromptBuilt,
    EXP_SeedsGenerated,
    EXP_CandidatePruned,
    EXP_SpaceBootstrapped,
)

logger = logging.getLogger(__name__)


class NLPService:
    """
    Core NLP subsystem.

    Responsibilities:
    - Manage the semantic vector space lifecycle (build / load / save)
    - Embed links, parent nodes, and target topics
    - Compute per-link feature vectors (nlp_vector)
    - Provide space-level signals for scoring pipeline
    - Accept batch updates from the space updater (never real-time)

    The space is STABLE during a crawl session.
    Only flush_buffer() mutates the space, and it must be called explicitly.
    """

    def __init__(
        self,
        blueprint_id: str,
        target_topic: str,
        llm_handler: LlmHandler,
        expansion_config,
        embedding_backend: str = "sentence_transformers",
        model_name: str = "all-MiniLM-L6-v2",
        store_base_dir: str = ".space_store",
        tracer=None,                          # TraceEmitter — optional, injected by Crawler
    ):
        
        self.blueprint_id = blueprint_id
        self.target_topic = target_topic

        self.engine: BaseEmbeddingEngine = create_embedding_engine(
            backend=embedding_backend,
            model_name=model_name
        )
        

        self.store = SpaceStore(base_dir=store_base_dir)
        self.extractor = FeatureExtractor()
        self.llm_handler = llm_handler
        self.prompt_builder = ExpansionPromptBuilder()
        self.space: Optional[VectorSpace] = None
        self.target_vec: Optional[np.ndarray] = None
        self.expansion_config = expansion_config
        self.llm_type = expansion_config["llm_type"]
        self.model_information = expansion_config["llm_model"]
        # update buffer: list of (key, vector, metadata)
        self._buffer: List[Tuple[str, np.ndarray, dict]] = []

        # tracer — emits NLP_* / EXP_* events; None = no-op
        self._tracer = tracer


    # internal helper — emit only if tracer attached
    async def _emit(self, event) -> None:
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

    async def build_space(self) -> None:
        """Bootstrap the space from the target topic.

        Generates seed sentences via LLM at init time.
        """
        target = self.target_topic

        t0 = time.monotonic()
        trace_id, node_id = get_trace()
        if not trace_id:
            trace_id = new_trace_id()
            node_id = f"bootstrap:{self.blueprint_id}"

        await self._emit(EXP_Triggered(
            trace_id=trace_id,
            node_id=node_id,
            blueprint_id=self.blueprint_id,
            target_topic=target,
            trigger_reason="new_blueprint",
        ))

        logger.info("Building new semantic space for '%s'", self.blueprint_id)
        self.space = VectorSpace(dim=self.engine.dim)
        target_vec = self.engine.encode(target)
        self.target_vec = target_vec

        expansions = await self.create_expansions(target, self.expansion_config)

        seeds = expansions.get("descriptions", [])
        await self._emit(EXP_SeedsGenerated(
            trace_id=trace_id,
            node_id=node_id,
            blueprint_id=self.blueprint_id,
            seed_count=len(seeds),
            seed_previews=[s[:80] for s in seeds],
            source="llm_expansion",
        ))

        seed_vectors = []
        for description in seeds:
            try:
                vec = self.engine.encode(description)
                key = f"seed::{self.blueprint_id}::{hash(description)}"
                seed_vectors.append((key, vec, {"type": "seed"}))
            except Exception:
                logger.exception("Failed to encode seed description: %r", description[:80])
                await self._emit(EXP_CandidatePruned(
                    trace_id=trace_id,
                    node_id=node_id,
                    blueprint_id=self.blueprint_id,
                    seed_preview=description[:80],
                    reason="error",
                    threshold=None,
                ))

        self.space.add_batch(seed_vectors)
        self.space.add_vector(
            key=f"__target__{self.blueprint_id}",
            vector=target_vec,
            metadata={"type": "target", "text": target},
        )

        self.save_space()

        duration_ms = (time.monotonic() - t0) * 1000
        await self._emit(EXP_SpaceBootstrapped(
            trace_id=trace_id,
            node_id=node_id,
            blueprint_id=self.blueprint_id,
            vectors_added=len(seed_vectors) + 1,
            space_version=self.space.version,
            duration_ms=duration_ms,
        ))

    async def create_expansions(self, target, expansion_config):
        trace_id, node_id = get_trace()

        prompt = self.prompt_builder.build(target, expansion_config)

        await self._emit(EXP_PromptBuilt(
            trace_id=trace_id,
            node_id=node_id,
            blueprint_id=self.blueprint_id,
            style= expansion_config.get("style", "balanced"),
            num_descriptions=expansion_config.get("num_descriptions", 6),
            prompt_len=len(prompt),
            prompt_preview=prompt[:300],
        ))

        context = ExpansionContext(
            self.llm_type,
            self.model_information,
            prompt,
        )
        logger.debug("Sending expansion request to LLM for '%s'", target)
        results = await self.llm_handler.send(context)
        return results

    def load_space(self) -> None:
        path = self.store.space_path(self.blueprint_id)
        self.space = VectorSpace(dim=self.engine.dim)
        self.space.load(path)
        self.target_vec = self.engine.encode(self.target_topic)
        logger.info("Loaded existing space: %s", self.space)

    def save_space(self) -> None:
        if self.space is None:
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
    # LINK SCORING (main pipeline hook)
    # =========================================================

    async def score_links(self, links: list, parent) -> list:
        if self.space is None:
            raise RuntimeError("NLPService.start() must be called before score_links()")

        trace_id, node_id = get_trace()

        parent_content = getattr(parent, "content", "") or ""
        parent_vec = self.engine.encode(parent_content) if parent_content else self.target_vec
        space_matrix = self.space.get_matrix()

        cluster_centroids = await self._get_cluster_centroids()

        for link in links:
            try:
                # --- input trace ---
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
                    trace_id=trace_id,
                    node_id=node_id,
                )

                link._nlp_score = await self._composite_score(
                    link.nlp_vector,
                    link_url=link.url,
                    trace_id=trace_id,
                    node_id=node_id,
                )

                # --- final score trace ---
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
    # VECTOR GENERATION (per link)
    # =========================================================

    async def generate_vector(
        self,
        link,
        parent_vec: np.ndarray,
        parent_content: str,
        space_matrix: np.ndarray,
        cluster_centroids: Dict[int, np.ndarray],
        trace_id: str = "",
        node_id: str = "",
    ) -> Dict[str, float]:
        link_text = f"[URL]{link.url} [ANCHOR]{link.anchor} [CTX]{link.context}"
        context_text = link.context or ""

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
        )
        # --- features trace ---
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
    # SPACE UPDATES (batch only — space remains stable until flush)
    # =========================================================

    def update_space(self, scoring_results: list) -> None:
        for link in scoring_results:
            expansions = getattr(link, "expansions", []) or []
            for i, sentence in enumerate(expansions):
                vec = self.engine.encode(sentence)
                self._buffer.append((
                    f"{link.url}::exp::{i}",
                    vec,
                    {"type": "expansion", "source_url": link.url, "text": sentence},
                ))
        logger.debug("Buffer has %d pending vectors", len(self._buffer))

    def flush_buffer(self) -> None:
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

    async def _get_cluster_centroids(self) -> Dict[int, np.ndarray]:
        if self.space is None or len(self.space) < 3:
            return {}
        clusters = self.space.get_clusters()
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
        features: Dict[str, float],
        link_url: str = "",
        trace_id: str = "",
        node_id: str = "",
    ) -> float:
        if not features:
            return 0.0
        


        weights = {
            "target_similarity": 0.85,
            "coverage_gap": 0.1,
            "novelty_injection": 0.05,
            "contextual_consistency": 0.05,
            "lexical_overlap": 0.05,
            "semantic_delta": -0.05,
            "region_density": -0.05,
            "cluster_distance": 0.00,
        }

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

    def get_space(self) -> Optional[VectorSpace]:
        return self.space

    def get_target_vec(self) -> Optional[np.ndarray]:
        return self.target_vec

    def buffer_size(self) -> int:
        return len(self._buffer)

    def space_size(self) -> int:
        return len(self.space) if self.space else 0

