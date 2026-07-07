import re

import numpy as np
from scipy.spatial.distance import cosine

from .vector_space import VectorSpace


class FeatureExtractor:
    """Computes all document-level features for a (link, parent, target) triple.

    Does NOT call the LLM. Pure math + embeddings. All inputs must
    already be embedded.
    """

    # =========================================================
    # LINK vs PARENT ANALYSIS
    # =========================================================

    def lexical_overlap(self, anchor: str, parent_content: str) -> float:
        """Token-level Jaccard overlap between anchor text and parent content.

        Returns:
            A value from 0.0 to 1.0.
        """
        if not anchor or not parent_content:
            return 0.0

        anchor_tokens = set(re.findall(r"\w+", anchor.lower()))
        parent_tokens = set(re.findall(r"\w+", parent_content.lower()))

        if not anchor_tokens or not parent_tokens:
            return 0.0

        intersection = anchor_tokens & parent_tokens
        union = anchor_tokens | parent_tokens
        return float(len(intersection) / len(union))

    def semantic_delta(
        self,
        link_vec: np.ndarray,
        parent_vec: np.ndarray,
    ) -> float:
        """How much does the link semantically diverge from its parent?

        High delta = exploration candidate.

        Returns:
            Cosine distance: 0 = same, 1 = orthogonal, 2 = opposite.
        """
        if link_vec is None or parent_vec is None:
            return 0.0
        return float(cosine(link_vec, parent_vec))

    def contextual_consistency(
        self,
        context_vec: np.ndarray,
        parent_vec: np.ndarray,
    ) -> float:
        """How consistent is the link's surrounding context with the parent node?

        Returns:
            Cosine similarity: 1 = identical context, 0 = unrelated.
        """
        if context_vec is None or parent_vec is None:
            return 0.0
        sim = 1.0 - cosine(context_vec, parent_vec)
        return float(max(0.0, sim))

    # =========================================================
    # LINK vs TARGET ANALYSIS
    # =========================================================

    def distance_to_nearest_cluster(
        self,
        link_vec: np.ndarray,
        cluster_centroids: dict[int, np.ndarray],
    ) -> float:
        if not cluster_centroids or link_vec is None:
            return 1.0
        distances = [
            cosine(link_vec, centroid)
            for centroid in cluster_centroids.values()
        ]
        return float(min(distances))

    def target_similarity(
        self, link_vec: np.ndarray, target_space: VectorSpace, top_k: int = 2
    ) -> float:
        """Mean similarity to the top-k nearest vectors in the target's
        semantic basis (report eq. 1 -- a basis rather than a single
        vector, since a topic is rarely well represented by one point).
        """
        if link_vec is None or len(target_space) == 0:
            return 0.0

        neighbors = target_space.similarity_search(query=link_vec, top_k=top_k)
        if not neighbors:
            return 0.0

        return float(np.mean([sim for _, sim in neighbors]))

    # =========================================================
    # GLOBAL SPACE ANALYSIS
    # =========================================================

    def region_density(
        self,
        link_vec: np.ndarray,
        space_matrix: np.ndarray,
        radius: float = 0.3,
    ) -> float:
        """What fraction of the space is within cosine distance `radius` of `link_vec`?

        Returns:
            0 for an isolated region, 1 for a saturated region.
        """
        if space_matrix is None or space_matrix.shape[0] == 0 or link_vec is None:
            return 0.0
        distances = np.array([cosine(link_vec, v) for v in space_matrix])
        nearby = np.sum(distances <= radius)
        return float(nearby / space_matrix.shape[0])

    def novelty_injection_score(
        self,
        link_vec: np.ndarray,
        space_matrix: np.ndarray,
        top_k: int = 5,
    ) -> float:
        """How novel is this vector relative to the current space?

        Returns:
            1.0 for fully novel, 0.0 for fully redundant.
        """
        if space_matrix is None or space_matrix.shape[0] == 0 or link_vec is None:
            return 1.0

        # top-k cosine similarities
        sims = np.array([1.0 - cosine(link_vec, v) for v in space_matrix])
        top_k_sims = np.sort(sims)[-top_k:]
        avg_top = float(np.mean(top_k_sims))
        return float(1.0 - avg_top)

    def coverage_gap_score(
        self,
        target_similarity: float,
        link_vec: np.ndarray,
        space_matrix: np.ndarray,
    ) -> float:
        """Estimate whether the link fills a gap between the current space and the target.

        A high score means the link sits in a region the space hasn't
        covered yet on the way toward the target.
        """
        if link_vec is None:
            return 0.0

        density = self.region_density(link_vec, space_matrix)

        # High target sim + low density = valuable coverage gap fill
        return float(target_similarity * (1.0 - density))

    # =========================================================
    # FULL FEATURE VECTOR
    # =========================================================

    def extract_all(
        self,
        link_vec: np.ndarray,
        anchor: str,
        context_vec: np.ndarray,
        parent_vec: np.ndarray,
        parent_content: str,
        space_matrix: np.ndarray,
        vector_space: VectorSpace,
        cluster_centroids: dict[int, np.ndarray] | None = None,
    ) -> dict[str, float]:
        """Compute the full feature vector for one link.

        Returns:
            A flat dict of every computed signal.
        """
        target_sim = self.target_similarity(link_vec, vector_space)

        return {
            # Link vs Parent
            "lexical_overlap": self.lexical_overlap(anchor, parent_content),
            "semantic_delta": self.semantic_delta(link_vec, parent_vec),
            "contextual_consistency": self.contextual_consistency(context_vec, parent_vec),

            # Link vs Target
            "target_similarity": target_sim,
            "cluster_distance": self.distance_to_nearest_cluster(link_vec, cluster_centroids or {}),

            # Global Space
            "region_density": self.region_density(link_vec, space_matrix),
            "novelty_injection": self.novelty_injection_score(link_vec, space_matrix),
            "coverage_gap": self.coverage_gap_score(target_sim, link_vec, space_matrix),
        }
