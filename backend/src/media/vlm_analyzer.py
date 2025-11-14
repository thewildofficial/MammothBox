"""Vision Language Model analyzer for image metadata extraction."""

import io
import json
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

from src.config.settings import get_settings
from src.media.embedder import MediaEmbedder

logger = logging.getLogger(__name__)


class VLMError(Exception):
    pass


@dataclass
class VLMMetadata:
    primary_category: str
    tags: List[str]  # 5-15 descriptive tags
    description: str  # 1-2 sentence summary
    detected_objects: List[Dict[str, Any]]  # [{name, confidence}]
    scene_type: str  # portrait, landscape, still life, action, abstract, indoor, outdoor
    color_palette: List[str]  # 3-5 dominant colors in hex
    suggested_cluster_name: str  # Human-readable grouping name
    vlm_model: str  # Model used
    fallback_used: bool = False  # True if CLIP fallback was used
    processing_time_ms: float = 0.0


@dataclass
class ClusterMetadata:
    cluster_name: str  # Human-readable name (2-4 words)
    description: str  # Brief description of commonality
    tags: List[str]  # 5-10 relevant tags
    primary_category: str  # Main category
    vlm_model: str  # Model used
    images_analyzed: int  # Number of representative images sent to VLM
    total_images: int  # Total images in cluster


class VLMAnalyzer:
    """Vision Language Model analyzer using Gemini 2.5 Flash."""

    # Predefined categories for CLIP zero-shot fallback
    CLIP_CATEGORIES = [
        "animal", "person", "vehicle", "nature", "food",
        "building", "object", "abstract", "landscape", "indoor scene"
    ]

    # Prompt for individual image analysis
    IMAGE_ANALYSIS_PROMPT = """Analyze this image and provide detailed structured metadata in JSON format.

Focus on:
1. **Primary Category**: Main subject category (animals, vehicles, nature, people, food, architecture, etc.)
2. **Descriptive Tags**: 5-15 diverse tags covering subjects, scene, activities, visual attributes, composition
3. **Description**: Concise 1-2 sentence summary
4. **Detected Objects**: Specific objects with confidence scores (0.0-1.0)
5. **Scene Type**: Classify as portrait, landscape, still life, action, abstract, indoor, or outdoor
6. **Color Palette**: 3-5 dominant colors in hex format (#RRGGBB)
7. **Suggested Cluster Name**: Human-readable name for grouping similar images (e.g., "Black Cats", "Mountain Sunsets")

Return ONLY valid JSON:
{
    "primary_category": "string",
    "tags": ["tag1", "tag2", ...],
    "description": "string",
    "detected_objects": [{"name": "string", "confidence": 0.0}],
    "scene_type": "string",
    "color_palette": ["#RRGGBB", ...],
    "suggested_cluster_name": "string"
}"""

    # Prompt template for cluster labeling (efficient approach from notebooks)
    CLUSTER_LABELING_PROMPT_TEMPLATE = """You are analyzing a cluster of {total_images} similar images. Below are {num_representative} representative images from this cluster.

Analyze these images and provide:
1. A concise cluster name (2-4 words, e.g., "Black Cats", "Red Sports Cars", "Mountain Landscapes")
2. A brief description of what these images have in common
3. Relevant tags (5-10 tags)
4. Primary category (e.g., "animals", "vehicles", "food", "nature", "architecture")

Return ONLY valid JSON:
{{
    "cluster_name": "string",
    "description": "string",
    "tags": ["tag1", "tag2"],
    "primary_category": "string"
}}"""

    def __init__(self):
        """Initialize VLM analyzer."""
        self.settings = get_settings()
        self._genai = None
        self._model = None
        self._embedder = None  # For CLIP fallback

        # Initialize Gemini if enabled and API key provided
        if self.settings.vlm_enabled and self.settings.gemini_api_key:
            self._init_gemini()

    def _init_gemini(self):
        """Initialize Google Generative AI SDK."""
        try:
            import google.generativeai as genai

            genai.configure(api_key=self.settings.gemini_api_key)
            self._genai = genai

            # Configure model with JSON output
            generation_config = {
                "temperature": 0.3,  # Lower temperature for consistency
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 2048,
                "response_mime_type": "application/json",
            }

            self._model = genai.GenerativeModel(
                model_name=self.settings.gemini_model,
                generation_config=generation_config
            )

            logger.info(
                f"Initialized Gemini model: {self.settings.gemini_model}")

        except ImportError:
            logger.error(
                "google-generativeai package not installed. VLM analysis disabled.")
            self.settings.vlm_enabled = False
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            self.settings.vlm_enabled = False

    def _get_embedder(self) -> MediaEmbedder:
        """Lazy load CLIP embedder for fallback."""
        if self._embedder is None:
            self._embedder = MediaEmbedder()
        return self._embedder

    def analyze_image(self, image: Image.Image) -> VLMMetadata:
        """
        Analyze individual image and extract structured metadata.

        Args:
            image: PIL Image (RGB)

        Returns:
            VLMMetadata with extracted information

        Raises:
            VLMError: If analysis fails completely
        """
        start_time = time.time()

        # Try VLM analysis first if enabled
        if self.settings.vlm_enabled and self._model:
            try:
                metadata = self._analyze_image_with_vlm(image)
                metadata.processing_time_ms = (time.time() - start_time) * 1000
                return metadata
            except Exception as e:
                logger.warning(
                    f"VLM analysis failed: {e}. Falling back to CLIP.")

                if not self.settings.vlm_fallback_to_clip:
                    raise VLMError(
                        f"VLM analysis failed and fallback disabled: {e}") from e

        # Fallback to CLIP zero-shot classification
        try:
            metadata = self._analyze_with_clip_fallback(image)
            metadata.processing_time_ms = (time.time() - start_time) * 1000
            logger.info(
                f"Used CLIP fallback for image (took {metadata.processing_time_ms:.2f}ms)")
            return metadata
        except Exception as e:
            raise VLMError(f"Both VLM and CLIP fallback failed: {e}") from e

    def _analyze_image_with_vlm(self, image: Image.Image) -> VLMMetadata:
        """Analyze individual image using Gemini VLM."""
        try:
            # Generate content with timeout
            response = self._model.generate_content(
                [self.IMAGE_ANALYSIS_PROMPT, image],
                request_options={"timeout": self.settings.vlm_timeout}
            )

            # Parse JSON response
            response_text = response.text.strip()
            metadata_dict = json.loads(response_text)

            # Validate and clean
            metadata_dict = self._validate_image_metadata(metadata_dict)

            # Create metadata object
            return VLMMetadata(
                primary_category=metadata_dict["primary_category"],
                tags=metadata_dict["tags"][:15],
                description=metadata_dict["description"],
                detected_objects=metadata_dict["detected_objects"],
                scene_type=metadata_dict["scene_type"],
                color_palette=metadata_dict["color_palette"],
                suggested_cluster_name=metadata_dict["suggested_cluster_name"],
                vlm_model=self.settings.gemini_model,
                fallback_used=False
            )

        except json.JSONDecodeError as e:
            raise VLMError(f"Failed to parse VLM JSON response: {e}") from e
        except KeyError as e:
            raise VLMError(f"VLM response missing required field: {e}") from e
        except Exception as e:
            raise VLMError(f"VLM analysis error: {e}") from e

    def _validate_image_metadata(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean VLM response for individual image."""
        # Ensure all required fields exist with fallback values
        data.setdefault("primary_category", "unknown")
        data.setdefault("tags", [])
        data.setdefault("description", "No description available")
        data.setdefault("detected_objects", [])
        data.setdefault("scene_type", "abstract")
        data.setdefault("color_palette", ["#808080", "#A0A0A0", "#C0C0C0"])
        data.setdefault("suggested_cluster_name", "Mixed Content")

        # Ensure tags is a list with content
        if not isinstance(data["tags"], list) or len(data["tags"]) == 0:
            data["tags"] = [data["primary_category"], "content"]

        # Limit tags to 15
        data["tags"] = data["tags"][:15]

        # Ensure detected_objects is a list
        if not isinstance(data["detected_objects"], list):
            data["detected_objects"] = []

        # Validate color palette format
        valid_colors = []
        for color in data.get("color_palette", []):
            if isinstance(color, str) and color.startswith("#") and len(color) == 7:
                valid_colors.append(color)

        if len(valid_colors) < 3:
            valid_colors.extend(["#808080", "#A0A0A0", "#C0C0C0"])

        data["color_palette"] = valid_colors[:5]

        return data

    def _analyze_with_clip_fallback(self, image: Image.Image) -> VLMMetadata:
        """Analyze image using CLIP zero-shot classification as fallback."""
        embedder = self._get_embedder()

        # Load CLIP model if not loaded
        if embedder._model is None:
            embedder._load_model()

        # Encode image
        image_embedding = embedder.encode_image(image)

        # Encode category text labels
        category_embeddings = embedder._model.encode(
            self.CLIP_CATEGORIES,
            batch_size=len(self.CLIP_CATEGORIES),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False
        )

        # Compute similarities
        similarities = np.dot(category_embeddings, image_embedding)

        # Get top category
        best_idx = np.argmax(similarities)
        best_category = self.CLIP_CATEGORIES[best_idx]
        confidence = float(similarities[best_idx])

        # Generate minimal metadata
        tags = [best_category, "content"]
        description = f"Image classified as {best_category} with {confidence:.2f} confidence."
        suggested_name = best_category.title() + "s"

        # Extract basic colors
        image_array = np.array(image.resize((100, 100)))
        if len(image_array.shape) == 3:
            colors = []
            for i in range(3):
                region = image_array[i*33:(i+1)*33, :, :]
                mean_color = region.mean(axis=(0, 1)).astype(int)
                hex_color = f"#{mean_color[0]:02x}{mean_color[1]:02x}{mean_color[2]:02x}"
                colors.append(hex_color)
        else:
            colors = ["#808080", "#A0A0A0", "#C0C0C0"]

        return VLMMetadata(
            primary_category=best_category,
            tags=tags,
            description=description,
            detected_objects=[
                {"name": best_category, "confidence": confidence}],
            scene_type="abstract",
            color_palette=colors,
            suggested_cluster_name=suggested_name,
            vlm_model="clip-fallback",
            fallback_used=True
        )

    def label_cluster(
        self,
        cluster_images: List[Image.Image],
        cluster_id: int,
        max_images: int = 5
    ) -> ClusterMetadata:
        """
        Efficient cluster labeling: Analyze multiple representative images.

        This is MUCH more efficient than labeling each image individually:
        - 1 API call per cluster instead of 1 per image
        - VLM sees multiple examples, produces better names
        - Reduces cost and latency significantly

        Approach from notebooks: cluster-first, then label.

        Args:
            cluster_images: List of images in the cluster
            cluster_id: Cluster identifier
            max_images: Max representative images to send (token limit)

        Returns:
            ClusterMetadata with human-readable name and tags
        """
        start_time = time.time()

        if not cluster_images:
            raise VLMError("No images provided for cluster labeling")

        # Try VLM labeling if enabled
        if self.settings.vlm_enabled and self._model:
            try:
                metadata = self._label_cluster_with_vlm(
                    cluster_images, cluster_id, max_images
                )
                processing_time_ms = (time.time() - start_time) * 1000
                logger.info(
                    f"Labeled cluster {cluster_id} with {len(cluster_images)} images "
                    f"(analyzed {metadata.images_analyzed}) in {processing_time_ms:.2f}ms"
                )
                return metadata
            except Exception as e:
                logger.warning(
                    f"VLM cluster labeling failed: {e}. Using fallback.")

        # Fallback to generic naming
        return ClusterMetadata(
            cluster_name=f"Cluster {cluster_id}",
            description="",
            tags=[],
            primary_category="unknown",
            vlm_model="fallback",
            images_analyzed=0,
            total_images=len(cluster_images)
        )

    def _label_cluster_with_vlm(
        self,
        cluster_images: List[Image.Image],
        cluster_id: int,
        max_images: int
    ) -> ClusterMetadata:
        """Label cluster using Gemini VLM with multiple representative images."""
        # Select representative images
        representative_images = cluster_images[:max_images]

        # Prepare images for Gemini API
        image_parts = []
        for img in representative_images:
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=90)
            buffer.seek(0)
            image_parts.append(
                {"mime_type": "image/jpeg", "data": buffer.getvalue()})

        # Format prompt with cluster info
        prompt = self.CLUSTER_LABELING_PROMPT_TEMPLATE.format(
            total_images=len(cluster_images),
            num_representative=len(representative_images)
        )

        try:
            response = self._model.generate_content(
                [prompt] + image_parts,
                request_options={"timeout": self.settings.vlm_timeout}
            )

            # Parse response
            payload = getattr(response, "text", None)
            if payload is None and getattr(response, "candidates", None):
                payload = response.candidates[0].content.parts[0].text

            metadata = json.loads(payload) if payload else {}

            return ClusterMetadata(
                cluster_name=metadata.get(
                    "cluster_name", f"Cluster {cluster_id}"),
                description=metadata.get("description", ""),
                tags=metadata.get("tags", [])[:10],  # Limit to 10
                primary_category=metadata.get("primary_category", "unknown"),
                vlm_model=self.settings.gemini_model,
                images_analyzed=len(representative_images),
                total_images=len(cluster_images)
            )

        except Exception as e:
            logger.error(f"VLM cluster labeling failed: {e}")
            raise VLMError(f"Failed to label cluster with VLM: {e}") from e

    def metadata_to_dict(self, metadata: VLMMetadata) -> Dict[str, Any]:
        """Convert VLMMetadata to dict for storage."""
        return asdict(metadata)

    def cluster_metadata_to_dict(self, metadata: ClusterMetadata) -> Dict[str, Any]:
        """Convert ClusterMetadata to dict for storage."""
        return asdict(metadata)
