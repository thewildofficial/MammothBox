"""
Tests for VLM analyzer module.

Tests VLM metadata extraction, cluster labeling, and CLIP fallback.
"""

import json
from unittest.mock import Mock, patch, MagicMock
import numpy as np
from PIL import Image
import pytest

from src.media.vlm_analyzer import (
    VLMAnalyzer,
    VLMMetadata,
    ClusterMetadata,
    VLMError
)


@pytest.fixture
def sample_image():
    """Create a simple test image."""
    return Image.new('RGB', (100, 100), color='red')


@pytest.fixture
def sample_images():
    """Create multiple test images."""
    return [
        Image.new('RGB', (100, 100), color='red'),
        Image.new('RGB', (100, 100), color='blue'),
        Image.new('RGB', (100, 100), color='green')
    ]


@pytest.fixture
def mock_settings():
    """Mock settings for VLM."""
    settings = Mock()
    settings.vlm_enabled = True
    settings.gemini_api_key = "test_api_key"
    settings.gemini_model = "gemini-2.5-flash"
    settings.vlm_timeout = 5
    settings.vlm_fallback_to_clip = True
    return settings


@pytest.fixture
def analyzer_with_mock_settings(mock_settings):
    """Create analyzer with mocked settings."""
    with patch('src.media.vlm_analyzer.get_settings', return_value=mock_settings):
        analyzer = VLMAnalyzer()
        return analyzer


class TestVLMAnalyzerInit:
    """Test VLM analyzer initialization."""

    def test_init_with_vlm_disabled(self):
        """Test initialization when VLM is disabled."""
        settings = Mock()
        settings.vlm_enabled = False
        settings.gemini_api_key = None

        with patch('src.media.vlm_analyzer.get_settings', return_value=settings):
            analyzer = VLMAnalyzer()
            assert analyzer._model is None
            assert analyzer._genai is None

    def test_init_with_no_api_key(self):
        """Test initialization when API key is missing."""
        settings = Mock()
        settings.vlm_enabled = True
        settings.gemini_api_key = None

        with patch('src.media.vlm_analyzer.get_settings', return_value=settings):
            analyzer = VLMAnalyzer()
            assert analyzer._model is None

    @patch('src.media.vlm_analyzer.VLMAnalyzer._init_gemini')
    def test_init_with_api_key(self, mock_init_gemini):
        """Test initialization calls _init_gemini when API key present."""
        settings = Mock()
        settings.vlm_enabled = True
        settings.gemini_api_key = "test_key"

        with patch('src.media.vlm_analyzer.get_settings', return_value=settings):
            analyzer = VLMAnalyzer()
            mock_init_gemini.assert_called_once()


class TestVLMImageAnalysis:
    """Test individual image analysis."""

    def test_analyze_image_with_vlm_success(self, analyzer_with_mock_settings, sample_image):
        """Test successful VLM analysis."""
        # Mock Gemini response
        mock_response = Mock()
        mock_response.text = json.dumps({
            "primary_category": "abstract",
            "tags": ["red", "square", "solid color", "geometric"],
            "description": "A solid red square image.",
            "detected_objects": [{"name": "square", "confidence": 0.95}],
            "scene_type": "abstract",
            "color_palette": ["#FF0000", "#FF3333", "#CC0000"],
            "suggested_cluster_name": "Red Abstracts"
        })

        analyzer_with_mock_settings._model = Mock()
        analyzer_with_mock_settings._model.generate_content.return_value = mock_response

        # Analyze
        metadata = analyzer_with_mock_settings.analyze_image(sample_image)

        # Verify
        assert isinstance(metadata, VLMMetadata)
        assert metadata.primary_category == "abstract"
        assert "red" in metadata.tags
        assert metadata.suggested_cluster_name == "Red Abstracts"
        assert not metadata.fallback_used
        assert metadata.vlm_model == "gemini-2.5-flash"
        assert metadata.processing_time_ms >= 0  # Mock execution is very fast

    def test_analyze_image_vlm_disabled_uses_clip(self, sample_image):
        """Test that CLIP fallback is used when VLM disabled."""
        settings = Mock()
        settings.vlm_enabled = False
        settings.vlm_fallback_to_clip = True

        with patch('src.media.vlm_analyzer.get_settings', return_value=settings):
            analyzer = VLMAnalyzer()

            # Mock MediaEmbedder
            with patch('src.media.vlm_analyzer.MediaEmbedder') as MockEmbedder:
                mock_embedder = Mock()
                mock_embedder._model = Mock()

                # Mock encode methods
                mock_embedder.encode_image.return_value = np.array(
                    [1.0] * 512, dtype=np.float32)
                mock_embedder._model.encode.return_value = np.array([
                    [0.1] * 512,  # animal
                    [0.9] * 512,  # person
                    [0.2] * 512,  # vehicle
                ], dtype=np.float32)

                MockEmbedder.return_value = mock_embedder
                analyzer._embedder = mock_embedder

                metadata = analyzer.analyze_image(sample_image)

                assert metadata.fallback_used
                assert metadata.vlm_model == "clip-fallback"
                assert metadata.primary_category in VLMAnalyzer.CLIP_CATEGORIES

    def test_analyze_image_vlm_error_fallback(self, analyzer_with_mock_settings, sample_image):
        """Test fallback to CLIP when VLM fails."""
        # Make VLM raise an error
        analyzer_with_mock_settings._model = Mock()
        analyzer_with_mock_settings._model.generate_content.side_effect = Exception(
            "API error")

        # Mock CLIP fallback
        with patch.object(analyzer_with_mock_settings, '_analyze_with_clip_fallback') as mock_clip:
            mock_clip.return_value = VLMMetadata(
                primary_category="abstract",
                tags=["content"],
                description="Fallback description",
                detected_objects=[],
                scene_type="abstract",
                color_palette=["#808080"],
                suggested_cluster_name="Abstracts",
                vlm_model="clip-fallback",
                fallback_used=True
            )

            metadata = analyzer_with_mock_settings.analyze_image(sample_image)

            assert metadata.fallback_used
            mock_clip.assert_called_once()

    def test_analyze_image_invalid_json_response(self, analyzer_with_mock_settings, sample_image):
        """Test handling of invalid JSON from VLM."""
        mock_response = Mock()
        mock_response.text = "Not valid JSON"

        analyzer_with_mock_settings._model = Mock()
        analyzer_with_mock_settings._model.generate_content.return_value = mock_response

        # Should fall back to CLIP
        with patch.object(analyzer_with_mock_settings, '_analyze_with_clip_fallback') as mock_clip:
            mock_clip.return_value = VLMMetadata(
                primary_category="abstract",
                tags=["content"],
                description="",
                detected_objects=[],
                scene_type="abstract",
                color_palette=["#808080"],
                suggested_cluster_name="Content",
                vlm_model="clip-fallback",
                fallback_used=True
            )

            metadata = analyzer_with_mock_settings.analyze_image(sample_image)
            assert metadata.fallback_used


class TestVLMClusterLabeling:
    """Test cluster labeling functionality."""

    def test_label_cluster_success(self, analyzer_with_mock_settings, sample_images):
        """Test successful cluster labeling."""
        # Mock Gemini response
        mock_response = Mock()
        mock_response.text = json.dumps({
            "cluster_name": "Colorful Abstracts",
            "description": "Abstract images with solid colors",
            "tags": ["abstract", "colorful", "geometric"],
            "primary_category": "abstract"
        })

        analyzer_with_mock_settings._model = Mock()
        analyzer_with_mock_settings._model.generate_content.return_value = mock_response

        # Label cluster
        metadata = analyzer_with_mock_settings.label_cluster(
            sample_images, cluster_id=1)

        # Verify
        assert isinstance(metadata, ClusterMetadata)
        assert metadata.cluster_name == "Colorful Abstracts"
        assert metadata.vlm_model == "gemini-2.5-flash"
        assert metadata.images_analyzed == 3
        assert metadata.total_images == 3
        assert "abstract" in metadata.tags

    def test_label_cluster_with_max_images(self, analyzer_with_mock_settings):
        """Test cluster labeling respects max_images limit."""
        # Create 10 images
        many_images = [Image.new('RGB', (100, 100), color='red')
                       for _ in range(10)]

        # Mock response
        mock_response = Mock()
        mock_response.text = json.dumps({
            "cluster_name": "Test Cluster",
            "description": "Test description",
            "tags": ["test"],
            "primary_category": "test"
        })

        analyzer_with_mock_settings._model = Mock()
        analyzer_with_mock_settings._model.generate_content.return_value = mock_response

        # Label with max 3 images
        metadata = analyzer_with_mock_settings.label_cluster(
            many_images, cluster_id=1, max_images=3)

        # Should only analyze 3 images
        assert metadata.images_analyzed == 3
        assert metadata.total_images == 10

    def test_label_cluster_empty_list(self, analyzer_with_mock_settings):
        """Test cluster labeling with empty image list raises error."""
        with pytest.raises(VLMError, match="No images provided"):
            analyzer_with_mock_settings.label_cluster([], cluster_id=1)

    def test_label_cluster_vlm_disabled(self, sample_images):
        """Test cluster labeling when VLM is disabled."""
        settings = Mock()
        settings.vlm_enabled = False
        settings.vlm_fallback_to_clip = True

        with patch('src.media.vlm_analyzer.get_settings', return_value=settings):
            analyzer = VLMAnalyzer()
            metadata = analyzer.label_cluster(sample_images, cluster_id=1)

            # Should use fallback
            assert metadata.cluster_name == "Cluster 1"
            assert metadata.vlm_model == "fallback"
            assert metadata.images_analyzed == 0

    def test_label_cluster_vlm_error(self, analyzer_with_mock_settings, sample_images):
        """Test cluster labeling handles VLM errors gracefully."""
        analyzer_with_mock_settings._model = Mock()
        analyzer_with_mock_settings._model.generate_content.side_effect = Exception(
            "API error")

        # Should use fallback
        metadata = analyzer_with_mock_settings.label_cluster(
            sample_images, cluster_id=1)
        assert metadata.cluster_name == "Cluster 1"
        assert metadata.vlm_model == "fallback"


class TestVLMMetadataValidation:
    """Test VLM metadata validation."""

    def test_validate_image_metadata_complete(self, analyzer_with_mock_settings):
        """Test validation with complete metadata."""
        data = {
            "primary_category": "animals",
            "tags": ["cat", "black", "fluffy"],
            "description": "A black fluffy cat",
            "detected_objects": [{"name": "cat", "confidence": 0.95}],
            "scene_type": "portrait",
            "color_palette": ["#000000", "#333333", "#666666"],
            "suggested_cluster_name": "Black Cats"
        }

        validated = analyzer_with_mock_settings._validate_image_metadata(data)

        assert validated["primary_category"] == "animals"
        assert len(validated["tags"]) == 3
        assert len(validated["color_palette"]) == 3

    def test_validate_image_metadata_missing_fields(self, analyzer_with_mock_settings):
        """Test validation fills in missing fields."""
        data = {}

        validated = analyzer_with_mock_settings._validate_image_metadata(data)

        # Should have fallback values
        assert validated["primary_category"] == "unknown"
        assert isinstance(validated["tags"], list)
        assert validated["scene_type"] == "abstract"
        assert len(validated["color_palette"]) >= 3

    def test_validate_image_metadata_invalid_colors(self, analyzer_with_mock_settings):
        """Test validation handles invalid color formats."""
        data = {
            "color_palette": ["invalid", "red", "#GGG123"]
        }

        validated = analyzer_with_mock_settings._validate_image_metadata(data)

        # Should have fallback colors
        assert len(validated["color_palette"]) >= 3
        assert all(c.startswith('#') and len(c) ==
                   7 for c in validated["color_palette"])

    def test_validate_image_metadata_too_many_tags(self, analyzer_with_mock_settings):
        """Test validation limits tags to 15."""
        data = {
            "tags": [f"tag{i}" for i in range(20)]
        }

        validated = analyzer_with_mock_settings._validate_image_metadata(data)

        assert len(validated["tags"]) == 15


class TestVLMMetadataConversion:
    """Test metadata conversion to dict."""

    def test_metadata_to_dict(self, analyzer_with_mock_settings):
        """Test VLMMetadata to dict conversion."""
        metadata = VLMMetadata(
            primary_category="animals",
            tags=["cat", "black"],
            description="A cat",
            detected_objects=[{"name": "cat", "confidence": 0.95}],
            scene_type="portrait",
            color_palette=["#000000"],
            suggested_cluster_name="Cats",
            vlm_model="gemini-2.5-flash",
            fallback_used=False,
            processing_time_ms=123.45
        )

        result = analyzer_with_mock_settings.metadata_to_dict(metadata)

        assert isinstance(result, dict)
        assert result["primary_category"] == "animals"
        assert result["vlm_model"] == "gemini-2.5-flash"
        assert result["fallback_used"] is False

    def test_cluster_metadata_to_dict(self, analyzer_with_mock_settings):
        """Test ClusterMetadata to dict conversion."""
        metadata = ClusterMetadata(
            cluster_name="Black Cats",
            description="Cluster of black cat images",
            tags=["cat", "black", "animal"],
            primary_category="animals",
            vlm_model="gemini-2.5-flash",
            images_analyzed=5,
            total_images=10
        )

        result = analyzer_with_mock_settings.cluster_metadata_to_dict(metadata)

        assert isinstance(result, dict)
        assert result["cluster_name"] == "Black Cats"
        assert result["images_analyzed"] == 5
        assert result["total_images"] == 10


class TestCLIPFallback:
    """Test CLIP fallback functionality."""

    def test_clip_fallback_categories(self, sample_image):
        """Test CLIP fallback uses predefined categories."""
        settings = Mock()
        settings.vlm_enabled = False
        settings.vlm_fallback_to_clip = True

        with patch('src.media.vlm_analyzer.get_settings', return_value=settings):
            analyzer = VLMAnalyzer()

            # Verify CLIP categories are defined
            assert len(analyzer.CLIP_CATEGORIES) > 0
            assert "animal" in analyzer.CLIP_CATEGORIES
            assert "vehicle" in analyzer.CLIP_CATEGORIES

    @patch('src.media.vlm_analyzer.MediaEmbedder')
    def test_clip_fallback_encoding(self, MockEmbedder, sample_image):
        """Test CLIP fallback performs encoding."""
        settings = Mock()
        settings.vlm_enabled = False
        settings.vlm_fallback_to_clip = True

        with patch('src.media.vlm_analyzer.get_settings', return_value=settings):
            analyzer = VLMAnalyzer()

            # Mock embedder
            mock_embedder = Mock()
            mock_embedder._model = Mock()
            mock_embedder.encode_image.return_value = np.array(
                [1.0] * 512, dtype=np.float32)
            mock_embedder._model.encode.return_value = np.array([
                [0.8] * 512,  # High similarity to first category
            ] + [[0.1] * 512] * 9, dtype=np.float32)

            MockEmbedder.return_value = mock_embedder
            analyzer._embedder = mock_embedder

            metadata = analyzer.analyze_image(sample_image)

            # Verify encoding was called
            mock_embedder.encode_image.assert_called_once()
            mock_embedder._model.encode.assert_called_once()
            assert metadata.primary_category in analyzer.CLIP_CATEGORIES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
