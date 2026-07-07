import logging
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy.spatial.distance import cosine
from sklearn.cluster import DBSCAN

logger = logging.getLogger(__name__)


@dataclass
class VectorEntry:
    key: str          # url or sentence hash
    vector: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorSpace:
    """Persistent semantic embedding space.

    Remains stable during a crawl session -- only batch-updated via flush.
    """

    def __init__(self, dim: int = 384):
        self.dim = dim
        self.entries: list[VectorEntry] = []
        self.matrix: np.ndarray | None = None  # shape (N, dim) -- rebuilt on demand
        self._dirty = False
        self.version: int = 0

    # =========================================================
    # CORE MUTATIONS
    # =========================================================

    def add_vector(
        self, key: str, vector: np.ndarray, metadata: dict[str, Any] | None = None
    ) -> None:
        """Add a single vector. Marks matrix as dirty (rebuild on next access)."""
        entry = VectorEntry(key=key, vector=vector, metadata=metadata or {})
        self.entries.append(entry)
        self._dirty = True

    def add_batch(self, entries: list[tuple[str, np.ndarray, dict[str, Any]]]) -> None:
        """Batch-add vectors efficiently."""
        for key, vec, meta in entries:
            self.entries.append(VectorEntry(key=key, vector=vec, metadata=meta))
        self._dirty = True
        self.version += 1

    # =========================================================
    # MATRIX ACCESS
    # =========================================================

    def _rebuild_matrix(self) -> None:
        if self.entries:
            self.matrix = np.vstack([e.vector for e in self.entries])
        else:
            self.matrix = np.empty((0, self.dim))
        self._dirty = False

    def get_matrix(self) -> np.ndarray:
        if self._dirty or self.matrix is None:
            self._rebuild_matrix()
        return self.matrix

    # =========================================================
    # SIMILARITY SEARCH
    # =========================================================

    def similarity_search(
        self,
        query: np.ndarray,
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> list[tuple[str, float]]:
        """Find the entries most similar to `query`.

        Returns:
            (key, similarity) pairs sorted by descending similarity, where
            similarity = 1 - cosine_distance.
        """
        mat = self.get_matrix()
        if mat.shape[0] == 0:
            return []

        # cosine similarity via broadcasting
        norms_mat = np.linalg.norm(mat, axis=1, keepdims=True)
        norm_q = np.linalg.norm(query)

        # avoid zero division
        safe_norms = np.where(norms_mat == 0, 1e-9, norms_mat)
        safe_q = query / (norm_q + 1e-9)
        normalized = mat / safe_norms

        similarities = normalized @ safe_q  # (N,)

        results = [
            (self.entries[i].key, float(similarities[i]))
            for i in range(len(self.entries))
            if similarities[i] >= threshold
        ]
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def mean_similarity(self, query: np.ndarray) -> float:
        """Average cosine similarity of `query` to every vector in the space."""
        mat = self.get_matrix()
        if mat.shape[0] == 0:
            return 0.0
        sims = [1 - cosine(query, e.vector) for e in self.entries]
        return float(np.mean(sims))

    def novelty_score(self, query: np.ndarray, top_k: int = 5) -> float:
        """How novel is `query` relative to the space?

        Returns:
            A score from 0.0 (not novel) to 1.0 (very novel).
        """
        results = self.similarity_search(query, top_k=top_k)
        if not results:
            return 1.0
        top_sim = results[0][1]
        return float(1.0 - top_sim)

    def density_score(self, query: np.ndarray, radius: float = 0.3) -> float:
        """Fraction of space vectors within cosine distance `radius` of `query`.

        Measures how dense the region around `query` is.
        """
        mat = self.get_matrix()
        if mat.shape[0] == 0:
            return 0.0
        distances = np.array([cosine(query, e.vector) for e in self.entries])
        count_nearby = np.sum(distances <= radius)
        return float(count_nearby / len(self.entries))

    # =========================================================
    # CLUSTERING
    # =========================================================

    def get_clusters(
        self,
        eps: float = 0.3,
        min_samples: int = 2,
    ) -> dict[int, list[str]]:
        """Run DBSCAN clustering on the current space.

        Returns:
            A mapping of cluster_id to the keys in that cluster.
            cluster_id == -1 means noise/outliers.
        """
        mat = self.get_matrix()
        if mat.shape[0] < 2:
            return {}

        db = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine")
        labels = db.fit_predict(mat)

        clusters: dict[int, list[str]] = {}
        for idx, label in enumerate(labels):
            clusters.setdefault(int(label), []).append(self.entries[idx].key)

        return clusters

    def coverage_gap_score(self, query: np.ndarray) -> float:
        """Estimate whether `query` falls in an under-covered region.

        Uses the inverse of density as a proxy.
        """
        density = self.density_score(query)
        return float(1.0 - density)

    # =========================================================
    # PERSISTENCE
    # =========================================================

    def save(self, path: str) -> None:
        """Pickle the entire space, including version metadata, to `path`."""
        payload = {
            "version": self.version,
            "dim": self.dim,
            "entries": self.entries,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info("Saved %d vectors (v%d) to %s", len(self.entries), self.version, path)

    def load(self, path: str) -> None:
        """Load a previously saved space from `path`, replacing current state."""
        with open(path, "rb") as f:
            payload = pickle.load(f)
        self.version = payload["version"]
        self.dim = payload["dim"]
        self.entries = payload["entries"]
        self._dirty = True  # force matrix rebuild
        logger.info("Loaded %d vectors (v%d) from %s", len(self.entries), self.version, path)

    @staticmethod
    def exists(path: str) -> bool:
        return Path(path).exists()

    # =========================================================
    # INTROSPECTION
    # =========================================================

    def __len__(self) -> int:
        return len(self.entries)

    def __repr__(self) -> str:
        return f"<VectorSpace entries={len(self.entries)} dim={self.dim} version={self.version}>"
