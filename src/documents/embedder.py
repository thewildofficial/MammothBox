"""Document chunk embedding utilities."""

from __future__ import annotations

from typing import Iterable, List, Sequence, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sentence_transformers import SentenceTransformer


class DocumentEmbeddingError(Exception):
    """Raised when embedding generation fails."""


class DocumentEmbedder:
    """Wrapper around SentenceTransformer for text/document embeddings."""

    def __init__(self, model_name: str = "all-MiniLM-L12-v2"):
        self.model_name = model_name
        self.embedding_dim = 768
        self._model = None

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - optional during tests
                raise DocumentEmbeddingError(
                    "The 'sentence-transformers' package is required for document embeddings."
                ) from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_chunks(self, chunks: Sequence[dict]) -> np.ndarray:
        """Generate embeddings for a collection of chunk dictionaries."""
        texts = [chunk.get("text", "") for chunk in chunks if chunk.get("text")]
        if not texts:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)

        try:
            model = self._get_model()
            embeddings = model.encode(
                texts,
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            return embeddings.astype(np.float32)
        except Exception as exc:  # pragma: no cover - delegated to model internals
            raise DocumentEmbeddingError(f"Failed to embed document chunks: {exc}") from exc

    def embed_query(self, query: str) -> np.ndarray:
        """Generate an embedding vector for a search query."""
        if not query:
            raise DocumentEmbeddingError("Query text cannot be empty")

        try:
            model = self._get_model()
            embedding = model.encode(
                [query],
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            return embedding[0].astype(np.float32)
        except Exception as exc:
            raise DocumentEmbeddingError(f"Failed to embed query: {exc}") from exc

