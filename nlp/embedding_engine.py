import hashlib
import logging
import re
from abc import ABC, abstractmethod

import numpy as np

logger = logging.getLogger(__name__)


# =========================================================
# ABSTRACT INTERFACE
# =========================================================

class BaseEmbeddingEngine(ABC):
    """Abstract interface for any embedding backend."""

    @abstractmethod
    def encode(self, texts: str | list[str]) -> np.ndarray:
        """Encode text(s) into embedding vector(s).

        Returns:
            An array of shape (dim,) for a single string, or (N, dim) for a list.
        """

    @property
    @abstractmethod
    def dim(self) -> int:
        """Embedding dimension."""


# =========================================================
# SENTENCE-TRANSFORMERS BACKEND (DEFAULT)
# =========================================================

class SentenceTransformerEngine(BaseEmbeddingEngine):
    """Wraps sentence-transformers. Lazy-loaded on first use.

    Default model: all-MiniLM-L6-v2 (384d, fast, strong).

    Loaded with local_files_only=True, so the model must already be
    cached (e.g. `python -c "from sentence_transformers import
    SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"`)
    before the first crawl -- see the README setup steps.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self._dim: int = 384

    def _load(self) -> None:
        if self._model is None:
            # Deliberately local: sentence-transformers pulls in a full ML
            # stack, so we don't pay that import cost for backends/crawls
            # that never actually use this engine.
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                self.model_name, local_files_only=True, device="cpu"
            )
            self._dim = self._model.get_sentence_embedding_dimension()
            logger.info("Loaded embedding model '%s' (dim=%d)", self.model_name, self._dim)

    def encode(self, texts: str | list[str]) -> np.ndarray:
        self._load()
        if isinstance(texts, str):
            texts = [texts]
            result = self._model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
            return result[0]  # shape (dim,)
        return self._model.encode(texts, show_progress_bar=False, convert_to_numpy=True)

    @property
    def dim(self) -> int:
        return self._dim


# =========================================================
# HASHING BACKEND (TESTS, OFFLINE RUNS)
# =========================================================

class HashingEmbeddingEngine(BaseEmbeddingEngine):
    """Deterministic bag-of-words embedding: each token is hashed into a
    bucket, counts are L2-normalised. Texts that share words are close,
    texts that share none are orthogonal. Needs no model, network or ML
    stack, so scoring, bucketing and space updates can be tested without
    sentence-transformers."""

    def __init__(self, dim: int = 64):
        self._dim = dim

    def _one(self, text: str) -> np.ndarray:
        vec = np.zeros(self._dim, dtype=np.float32)
        for tok in re.findall(r"\w+", text.lower()):
            h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big")
            vec[h % self._dim] += 1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm else vec

    def encode(self, texts: str | list[str]) -> np.ndarray:
        if isinstance(texts, str):
            return self._one(texts)
        return np.stack([self._one(t) for t in texts]) if texts else np.zeros((0, self._dim), np.float32)

    @property
    def dim(self) -> int:
        return self._dim


# =========================================================
# FACTORY
# =========================================================

def create_embedding_engine(
    backend: str = "sentence_transformers", **kwargs
) -> BaseEmbeddingEngine:
    """Factory function. Extend here to add new backends."""
    if backend == "sentence_transformers":
        model = kwargs.get("model_name", "all-MiniLM-L6-v2")
        return SentenceTransformerEngine(model_name=model)
    if backend == "hashing":
        return HashingEmbeddingEngine(dim=kwargs.get("dim", 64))
    raise ValueError(f"Unknown embedding backend: {backend!r}")
