"""
Unit tests for media embedder.
"""

import pytest
import numpy as np
from PIL import Image

from src.media.embedder import MediaEmbedder, EmbeddingError


@pytest.fixture
def embedder():
    """Create a media embedder."""
    return MediaEmbedder()


def create_test_image():
    """Create a test image."""
    return Image.new('RGB', (224, 224), color='red')


def test_encode_image(embedder):
    """Test image encoding."""
    image = create_test_image()
    
    embedding = embedder.encode_image(image)
    
    assert embedding.shape == (512,)
    assert embedding.dtype == np.float32
    # Check normalization (L2 norm should be ~1.0)
    norm = np.linalg.norm(embedding)
    assert abs(norm - 1.0) < 0.1  # Allow small tolerance


def test_encode_images_batch(embedder):
    """Test batch image encoding."""
    images = [create_test_image() for _ in range(3)]
    
    embeddings = embedder.encode_images_batch(images)
    
    assert len(embeddings) == 3
    for emb in embeddings:
        assert emb.shape == (512,)
        assert emb.dtype == np.float32


def test_encode_text(embedder):
    """Test text encoding."""
    text = "a red car"
    
    embedding = embedder.encode_text(text)
    
    assert embedding.shape == (512,)
    assert embedding.dtype == np.float32


def test_encode_video_keyframes(embedder):
    """Test video keyframe encoding."""
    keyframes = [create_test_image() for _ in range(3)]
    
    mean_embedding, frame_embeddings = embedder.encode_video_keyframes(keyframes)
    
    assert mean_embedding.shape == (512,)
    assert len(frame_embeddings) == 3
    for emb in frame_embeddings:
        assert emb.shape == (512,)

