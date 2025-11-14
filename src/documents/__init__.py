"""Document processing package."""

from .parser import DocumentParser, DocumentParserError  # noqa: F401
from .chunker import DocumentChunker  # noqa: F401
from .embedder import DocumentEmbedder, DocumentEmbeddingError  # noqa: F401

try:  # pragma: no cover - optional import
    from .service import DocumentService, DocumentServiceError  # noqa: F401
except Exception:  # pragma: no cover
    DocumentService = None
    DocumentServiceError = None

__all__ = [
    "DocumentParser",
    "DocumentParserError",
    "DocumentChunker",
    "DocumentEmbedder",
    "DocumentEmbeddingError",
]

if DocumentService is not None:
    __all__.extend(["DocumentService", "DocumentServiceError"])

