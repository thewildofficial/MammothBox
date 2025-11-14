"""Structure-aware document chunking utilities."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

try:
    from langchain_text_splitters import (
        MarkdownHeaderTextSplitter,
        RecursiveCharacterTextSplitter,
    )
except ImportError:  # pragma: no cover - optional dependency
    MarkdownHeaderTextSplitter = None
    RecursiveCharacterTextSplitter = None


class _SimpleTextSplitter:
    """Fallback splitter used when langchain is unavailable."""

    def __init__(self, chunk_size: int, chunk_overlap: int):
        self.chunk_size = chunk_size
        self.chunk_overlap = min(chunk_overlap, chunk_size // 2)

    def split_text(self, text: str) -> List[str]:
        if not text:
            return []
        chunks: List[str] = []
        start = 0
        length = len(text)
        step = max(1, self.chunk_size - self.chunk_overlap)
        while start < length:
            chunks.append(text[start : start + self.chunk_size])
            start += step
        return chunks


class DocumentChunker:
    """Split parsed document elements into search-friendly chunks."""

    HEADING_TYPES = {"title", "heading", "header", "sectionheader"}

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        if RecursiveCharacterTextSplitter:
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
        else:
            self.text_splitter = _SimpleTextSplitter(chunk_size, chunk_overlap)

        if MarkdownHeaderTextSplitter:
            self.markdown_splitter = MarkdownHeaderTextSplitter(
                headers_to_split_on=[("#", "Header 1"), ("##", "Header 2"), ("###", "Header 3")]
            )
        else:
            self.markdown_splitter = None

    def chunk_elements(self, elements: Iterable[Dict], doc_id: str) -> List[Dict]:
        """Chunk parsed elements while preserving heading context."""
        chunks: List[Dict] = []
        current_heading: Optional[str] = None
        chunk_index = 0

        for element in elements:
            element_type = (element.get("type") or "Unknown").strip()
            text = (element.get("text") or "").strip()
            metadata = element.get("metadata") or {}

            if not text:
                continue

            if element_type.lower() in self.HEADING_TYPES:
                current_heading = text
                continue

            fragments = self._split_text(text, metadata)

            for fragment in fragments:
                if not fragment.strip():
                    continue

                chunks.append(
                    {
                        "doc_id": doc_id,
                        "text": fragment.strip(),
                        "chunk_index": chunk_index,
                        "parent_heading": current_heading,
                        "page_number": metadata.get("page_number"),
                        "element_type": element_type,
                    }
                )
                chunk_index += 1

        return chunks

    def _split_text(self, text: str, metadata: Dict) -> List[str]:
        """Split text using markdown-aware heuristics when possible."""
        if self.markdown_splitter and metadata.get("filetype", "").lower() in {"md", "markdown"}:
            markdown_sections = self.markdown_splitter.split_text(text)
            combined_sections = [
                "\n".join(filter(None, [section.metadata.get("Header 1"), section.page_content]))
                for section in markdown_sections
            ]
            return self.text_splitter.split_text("\n\n".join(combined_sections))

        return self.text_splitter.split_text(text)

