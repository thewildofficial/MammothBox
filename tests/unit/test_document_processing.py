import io
from types import SimpleNamespace

import numpy as np
import pytest

from src.documents.parser import DocumentParser
from src.documents.chunker import DocumentChunker
from src.documents.embedder import (
    DocumentEmbedder,
    DocumentEmbeddingError,
    SCHEMA_EMBEDDING_DIM,
)


def _mock_embedder_backend(monkeypatch):
    class FakeModel:
        def encode(self, texts, **kwargs):
            return np.ones((len(texts), SCHEMA_EMBEDDING_DIM), dtype=np.float32)

    def fake_get_model(self):
        self.embedding_dim = SCHEMA_EMBEDDING_DIM
        return FakeModel()

    monkeypatch.setattr(DocumentEmbedder, "_get_model", fake_get_model, raising=False)


def test_document_parser_normalizes_elements(monkeypatch):
    parser = DocumentParser()

    class DummyElement:
        category = "Paragraph"
        metadata = SimpleNamespace(
            to_dict=lambda: {"page_number": 2, "filetype": "pdf"},
        )

        def __str__(self):
            return "Hello world"

    monkeypatch.setattr(
        "src.documents.parser.partition",
        lambda **kwargs: [DummyElement()],
    )

    elements = parser.parse(io.BytesIO(b"hello"), filename="sample.pdf")
    assert len(elements) == 1
    assert elements[0].type == "Paragraph"
    assert elements[0].metadata["page_number"] == 2


def test_document_chunker_preserves_headings():
    chunker = DocumentChunker(chunk_size=50, chunk_overlap=0)
    elements = [
        {"type": "Title", "text": "Doc Title", "metadata": {}},
        {
            "type": "Paragraph",
            "text": "This is a long paragraph that should be chunked.",
            "metadata": {"page_number": 1},
        },
    ]

    chunks = chunker.chunk_elements(elements, "doc-123")
    assert len(chunks) >= 1
    assert chunks[0]["parent_heading"] == "Doc Title"
    assert chunks[0]["page_number"] == 1


def test_document_embedder_shapes(monkeypatch):
    _mock_embedder_backend(monkeypatch)
    embedder = DocumentEmbedder(model_name="sentence-transformers/all-mpnet-base-v2")

    embeddings = embedder.embed_chunks([{"text": "chunk text"}])
    assert embeddings.shape == (1, SCHEMA_EMBEDDING_DIM)


def test_document_embedder_rejects_missing_text(monkeypatch):
    _mock_embedder_backend(monkeypatch)
    embedder = DocumentEmbedder(model_name="sentence-transformers/all-mpnet-base-v2")

    with pytest.raises(DocumentEmbeddingError) as excinfo:
        embedder.embed_chunks([
            {"text": "okay"},
            {"text": "   "},
            {},
        ])

    message = str(excinfo.value)
    assert "chunk" in message
    assert "indexes: 1, 2" in message




