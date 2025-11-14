"""Document chunk embedding utilities."""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sentence_transformers import SentenceTransformer


class DocumentEmbeddingError(Exception):
    """Raised when embedding generation fails."""


SCHEMA_EMBEDDING_DIM = 768


class DocumentEmbedder:
    """Wrapper around SentenceTransformer for text/document embeddings."""

    def __init__(self, model_name: str = "sentence-transformers/all-mpnet-base-v2"):
        self.model_name = model_name
        self.embedding_dim: Optional[int] = None
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

            embedding_dim = self._model.get_sentence_embedding_dimension()
            if embedding_dim != SCHEMA_EMBEDDING_DIM:
                # Reset cached model to avoid using an incompatible embedding size
                self._model = None
                raise DocumentEmbeddingError(
                    "Model embedding dimension {0} does not match schema dimension {1}. "
                    "Update the database schema or choose a compatible model."
                    .format(embedding_dim, SCHEMA_EMBEDDING_DIM)
                )

            self.embedding_dim = embedding_dim
        return self._model

    def _ensure_embedding_dim(self) -> int:
        if self.embedding_dim is None:
            # Lazily load the model solely to establish a validated dimension
            self._get_model()
        return self.embedding_dim or SCHEMA_EMBEDDING_DIM

    def embed_chunks(self, chunks: Sequence[dict]) -> np.ndarray:
        """Generate embeddings for a collection of chunk dictionaries."""
        if not chunks:
            target_dim = self._ensure_embedding_dim()
            return np.zeros((0, target_dim), dtype=np.float32)

        invalid_indexes: List[int] = []
        texts: List[str] = []

        for idx, chunk in enumerate(chunks):
            if not isinstance(chunk, dict):
                invalid_indexes.append(idx)
                continue

            text = chunk.get("text")
            if not isinstance(text, str) or not text.strip():
                invalid_indexes.append(idx)
                continue

            texts.append(text)

        if invalid_indexes:
            preview = ", ".join(str(i) for i in invalid_indexes[:5])
            raise DocumentEmbeddingError(
                "Chunk text validation failed for {count} chunk(s); first bad indexes: {indexes}".format(
                    count=len(invalid_indexes),
                    indexes=preview,
                )
            )

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

