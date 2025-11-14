import io
from types import SimpleNamespace

import numpy as np
import pytest

from src.documents.parser import DocumentParser
from src.documents.chunker import DocumentChunker
from src.documents.embedder import DocumentEmbedder


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
    embedder = DocumentEmbedder()

    class FakeModel:
        def encode(self, texts, **kwargs):
            return np.ones((len(texts), embedder.embedding_dim), dtype=np.float32)

    monkeypatch.setattr(
        DocumentEmbedder,
        "_get_model",
        lambda self: FakeModel(),
    )

    embeddings = embedder.embed_chunks([{"text": "chunk text"}])
    assert embeddings.shape == (1, embedder.embedding_dim)




