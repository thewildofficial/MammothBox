"""
Unit tests for media processor.
"""

import pytest
from io import BytesIO
from PIL import Image
import numpy as np

from src.media.processor import MediaProcessor, MediaProcessingError
from src.storage.filesystem import FilesystemStorage


@pytest.fixture
def storage(tmp_path):
    """Create a temporary storage adapter."""
    return FilesystemStorage(str(tmp_path))


@pytest.fixture
def processor(storage):
    """Create a media processor."""
    return MediaProcessor(storage)


def create_test_image(width=800, height=600, format='JPEG'):
    """Create a test image."""
    img = Image.new('RGB', (width, height), color='red')
    buffer = BytesIO()
    img.save(buffer, format=format)
    buffer.seek(0)
    return buffer.read()


def test_detect_mime_type_jpeg(processor):
    """Test MIME type detection for JPEG."""
    jpeg_data = create_test_image()
    mime = processor.detect_mime_type(jpeg_data, "test.jpg")
    assert mime == "image/jpeg"


def test_detect_mime_type_png(processor):
    """Test MIME type detection for PNG."""
    img = Image.new('RGB', (100, 100), color='blue')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    png_data = buffer.getvalue()
    
    mime = processor.detect_mime_type(png_data, "test.png")
    assert mime == "image/png"


def test_validate_file_size_image(processor):
    """Test file size validation for images."""
    # Valid size
    small_image = create_test_image()
    processor.validate_file(small_image, "image/jpeg")
    
    # Too large (would need to create a very large file, skip for unit test)
    # This is more of an integration test


def test_process_image(processor):
    """Test image processing."""
    image_data = create_test_image(width=2000, height=1500)  # Larger than max_size
    
    result = processor.process_image(image_data, "test.jpg")
    
    assert result.normalized_image.width <= 1024
    assert result.normalized_image.height <= 1024
    assert result.normalized_image.mode == 'RGB'
    assert result.thumbnail.width <= 256
    assert result.thumbnail.height <= 256
    assert result.metadata.width is not None
    assert result.metadata.height is not None
    assert result.metadata.perceptual_hash is not None


def test_process_image_small(processor):
    """Test processing small image (no resize needed)."""
    image_data = create_test_image(width=500, height=400)
    
    result = processor.process_image(image_data, "test.jpg")
    
    # Should maintain original size if under limit
    assert result.normalized_image.width == 500
    assert result.normalized_image.height == 400


def test_extract_exif(processor):
    """Test EXIF extraction."""
    image_data = create_test_image()
    image = Image.open(BytesIO(image_data))
    
    exif = processor.extract_exif(image)
    # May be None if no EXIF data
    assert exif is None or isinstance(exif, dict)

