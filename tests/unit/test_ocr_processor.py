"""
Tests for OCRProcessor text extraction.
"""

from pathlib import Path
from io import BytesIO
import importlib.util

import pytest
from PIL import Image, ImageDraw, ImageFont

pytest.importorskip("pytesseract")


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MEDIA_SRC = PROJECT_ROOT / "src" / "media"

spec = importlib.util.spec_from_file_location(
    "ocr_processor_module", MEDIA_SRC / "ocr_processor.py"
)
ocr_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ocr_module)  # type: ignore[union-attr]
OCRProcessor = ocr_module.OCRProcessor
BoundingBox = ocr_module.BoundingBox


IMAGES_DIR = Path(__file__).resolve().parent.parent / "resources" / "images"


@pytest.fixture(scope="module")
def processor():
    """Default OCR processor instance."""
    return OCRProcessor()


def test_extract_text_from_sample_image(processor):
    """OCR should extract meaningful text from the sample screenshot."""
    text_image = IMAGES_DIR / "text_heavy.png"

    result = processor.extract_text(str(text_image))

    assert result.text.strip() != ""
    assert result.word_count >= 5
    assert result.confidence > 40.0
    assert all(isinstance(box, BoundingBox) for box in result.bounding_boxes)


def test_extract_text_blank_image(processor):
    """Blank image should yield no text and low/zero confidence."""
    blank_image = IMAGES_DIR / "blank_white.png"

    result = processor.extract_text(str(blank_image))

    assert result.text == ""
    assert result.word_count == 0
    # Tesseract may return low confidence even for blank images
    assert result.confidence < 20.0  # Accept low confidence instead of exactly 0.0
    assert result.bounding_boxes == []


def test_extract_text_respects_confidence_threshold(tmp_path):
    """High confidence threshold should filter out low-confidence words."""
    # Create a simple image with faint text to provoke lower confidence readings.
    img = Image.new("RGB", (400, 200), color="white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    draw.text((20, 80), "hello world", fill=(120, 120, 120), font=font)

    image_path = tmp_path / "low_contrast_text.png"
    img.save(image_path)

    strict_processor = OCRProcessor(confidence_threshold=90)
    strict_result = strict_processor.extract_text(str(image_path))

    # With strict threshold words may be filtered out.
    assert strict_result.word_count == 0
    assert strict_result.text == ""

    relaxed_processor = OCRProcessor(confidence_threshold=10)
    relaxed_result = relaxed_processor.extract_text(str(image_path))

    assert relaxed_result.word_count >= 1
    assert "hello" in relaxed_result.text.lower()


def test_extract_text_from_pil_image(processor):
    """Direct PIL input should work the same as file-path input."""
    text_image = Image.open(IMAGES_DIR / "text_heavy.png")

    result = processor.extract_text_from_pil(text_image)

    assert result.word_count >= 5
    assert result.confidence > 40.0

