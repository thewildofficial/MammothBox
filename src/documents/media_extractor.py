"""Utilities for extracting embedded images from documents."""

from __future__ import annotations

import io
import logging
from typing import Dict, List

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTImage, LTFigure
from PIL import Image

logger = logging.getLogger(__name__)


class EmbeddedMediaExtractor:
    """Extract embedded images from supported document formats."""

    def extract_from_pdf(self, file_obj: io.BytesIO) -> List[Dict]:
        file_obj.seek(0)
        images: List[Dict] = []

        try:
            for page_number, page_layout in enumerate(extract_pages(file_obj), start=1):
                for element in page_layout:
                    self._collect_pdf_images(element, page_number, images)
        except Exception as exc:  # pragma: no cover - pdfminer internals
            logger.warning("PDF image extraction failed: %s", exc)
        finally:
            file_obj.seek(0)

        return images

    def _collect_pdf_images(self, element, page_number: int, images: List[Dict]) -> None:
        if isinstance(element, LTImage):
            try:
                stream_data = element.stream.get_data()
                image = Image.open(io.BytesIO(stream_data))
                images.append(
                    {
                        "image": image,
                        "page_number": page_number,
                        "width": image.width,
                        "height": image.height,
                        "format": image.format or "PNG",
                    }
                )
            except Exception as exc:  # pragma: no cover - corrupted image data
                logger.debug("Skipping embedded image: %s", exc)
        elif isinstance(element, LTFigure):
            for child in element:
                self._collect_pdf_images(child, page_number, images)

    def extract_from_docx(self, file_obj: io.BytesIO) -> List[Dict]:
        from docx import Document

        file_obj.seek(0)
        images: List[Dict] = []

        try:
            document = Document(file_obj)
            for rel in document.part.rels.values():
                if "image" not in rel.target_ref:
                    continue
                img_stream = io.BytesIO(rel.target_part.blob)
                try:
                    image = Image.open(img_stream)
                    images.append(
                        {
                            "image": image,
                            "page_number": None,
                            "width": image.width,
                            "height": image.height,
                            "format": image.format or "PNG",
                        }
                    )
                except Exception as exc:
                    logger.debug("Skipping DOCX embedded image: %s", exc)
        except Exception as exc:  # pragma: no cover - python-docx internals
            logger.warning("DOCX image extraction failed: %s", exc)
        finally:
            file_obj.seek(0)

        return images



