"""Document parsing utilities built on top of unstructured."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Dict, List, Optional

try:
    from unstructured.partition.auto import partition
except ImportError:  # pragma: no cover - dependency optional during tests
    partition = None


class DocumentParserError(Exception):
    """Raised when document parsing fails."""


@dataclass(frozen=True)
class ParsedElement:
    """Normalized representation of an extracted document element."""

    type: str
    text: str
    metadata: Dict[str, Optional[str]]


class DocumentParser:
    """Multi-format document parser using the `unstructured` library."""

    SUPPORTED_FORMATS = {
        ".pdf": "pdf",
        ".epub": "epub",
        ".docx": "docx",
        ".doc": "doc",
        ".pptx": "pptx",
        ".ppt": "ppt",
        ".txt": "text",
        ".md": "markdown",
        ".rtf": "rtf",
        ".html": "html",
    }

    def parse(self, file: BinaryIO, filename: str | None = None) -> List[ParsedElement]:
        """
        Parse a document stream and extract structured elements.

        Args:
            file: File-like object positioned at the beginning.
            filename: Optional filename used for format hints.

        Returns:
            List of ParsedElement objects.
        """
        # Keep the pointer intact for callers
        position = file.tell()
        file.seek(0)
        try:
            extension = Path(filename or "").suffix.lower()
            if extension and extension not in self.SUPPORTED_FORMATS:
                raise DocumentParserError(
                    f"Unsupported document format: {extension or 'unknown'}"
                )

            if partition is None:
                raise DocumentParserError(
                    "The 'unstructured' package is required for document parsing. "
                    "Install it by running `pip install unstructured`."
                )

            elements = partition(file=file, file_filename=filename)

            parsed: List[ParsedElement] = []
            for element in elements:
                text = str(element).strip()
                if not text:
                    continue

                metadata = {}
                if hasattr(element, "metadata") and element.metadata:
                    try:
                        metadata = element.metadata.to_dict()
                    except Exception:
                        metadata = {}

                parsed.append(
                    ParsedElement(
                        type=getattr(element, "category", element.__class__.__name__),
                        text=text,
                        metadata=metadata,
                    )
                )

            return parsed
        except DocumentParserError:
            raise
        except Exception as exc:  # pragma: no cover - defensive catch-all
            raise DocumentParserError(f"Failed to parse document: {exc}") from exc
        finally:
            file.seek(position)

