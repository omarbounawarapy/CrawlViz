import logging
import numpy as np
from abc import ABC, abstractmethod
from typing import List, Union

logger = logging.getLogger(__name__)


# =========================================================
# ABSTRACT INTERFACE
# =========================================================

class BaseEmbeddingEngine(ABC):
    """Abstract interface for any embedding backend."""

    @abstractmethod
    def encode(self, texts: Union[str, List[str]]) -> np.ndarray:
        """
        Encode text(s) into embedding vector(s).
        Returns np.ndarray of shape (dim,) for single string,
        or (N, dim) for list.
        """

    @property
    @abstractmethod
    def dim(self) -> int:
        """Embedding dimension."""


# =========================================================
# SENTENCE-TRANSFORMERS BACKEND (DEFAULT)
# =========================================================

class SentenceTransformerEngine(BaseEmbeddingEngine):
    """
    Wraps sentence-transformers. Lazy-loaded on first use.
    Default model: all-MiniLM-L6-v2 (384d, fast, strong)

    Loaded with local_files_only=True, so the model must already be
    cached (e.g. `python -c "from sentence_transformers import
    SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"`)
    before the first crawl -- see the README setup steps.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self._dim: int = 384

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                self.model_name, local_files_only=True, device="cpu"
            )
            self._dim = self._model.get_sentence_embedding_dimension()
            logger.info("Loaded embedding model '%s' (dim=%d)", self.model_name, self._dim)

    def encode(self, texts: Union[str, List[str]]) -> np.ndarray:
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
# FACTORY
# =========================================================

def create_embedding_engine(backend: str = "sentence_transformers", **kwargs) -> BaseEmbeddingEngine:
    """
    Factory function. Extend here to add new backends.
    """
    if backend == "sentence_transformers":
        model = kwargs.get("model_name", "all-MiniLM-L6-v2")
        return SentenceTransformerEngine(model_name=model)
    raise ValueError(f"Unknown embedding backend: {backend}")