"""
CLIP embedding generator for media files.

Loads CLIP model and generates normalized embeddings for images, videos, and audio.
"""

import logging
from typing import List, Optional, Tuple
import numpy as np
from PIL import Image

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Exception raised during embedding generation."""
    pass


class MediaEmbedder:
    """
    CLIP-based embedder for media files.
    
    Uses clip-ViT-B-32 model (512 dimensions) with CPU-optimized inference.
    Supports batch processing for efficiency.
    """
    
    def __init__(self):
        """Initialize embedder (lazy model loading)."""
        self.settings = get_settings()
        self._model = None
        self._model_name = "sentence-transformers/clip-ViT-B-32"
    
    def _load_model(self):
        """Lazy load CLIP model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading CLIP model: {self._model_name}")
                self._model = SentenceTransformer(self._model_name, device='cpu')
                logger.info("CLIP model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load CLIP model: {e}")
                raise EmbeddingError(f"Failed to load CLIP model: {e}") from e
    
    def encode_image(self, image: Image.Image) -> np.ndarray:
        """
        Encode a single image using CLIP image encoder.
        
        Args:
            image: PIL Image (RGB)
            
        Returns:
            512-dimensional normalized vector
        """
        self._load_model()
        
        try:
            # Encode image
            embedding = self._model.encode(
                image,
                batch_size=1,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False
            )
            
            # Ensure it's 1D array
            if embedding.ndim > 1:
                embedding = embedding.flatten()
            
            # Ensure correct dimension
            if len(embedding) != 512:
                raise EmbeddingError(f"Unexpected embedding dimension: {len(embedding)}")
            
            return embedding.astype(np.float32)
            
        except Exception as e:
            raise EmbeddingError(f"Failed to encode image: {e}") from e
    
    def encode_images_batch(self, images: List[Image.Image]) -> List[np.ndarray]:
        """
        Encode multiple images in batch for efficiency.
        
        Args:
            images: List of PIL Images (RGB)
            
        Returns:
            List of 512-dimensional normalized vectors
        """
        if not images:
            return []
        
        self._load_model()
        
        try:
            # Batch encode
            batch_size = 16  # As per spec
            embeddings = self._model.encode(
                images,
                batch_size=batch_size,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False
            )
            
            # Convert to list of arrays
            result = []
            for i in range(len(images)):
                emb = embeddings[i] if embeddings.ndim == 2 else embeddings
                if emb.ndim > 1:
                    emb = emb.flatten()
                result.append(emb.astype(np.float32))
            
            return result
            
        except Exception as e:
            raise EmbeddingError(f"Failed to encode images batch: {e}") from e
    
    def encode_text(self, text: str) -> np.ndarray:
        """
        Encode text query using CLIP text encoder (for search).
        
        Args:
            text: Query text
            
        Returns:
            512-dimensional normalized vector
        """
        self._load_model()
        
        try:
            embedding = self._model.encode(
                text,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False
            )
            
            if embedding.ndim > 1:
                embedding = embedding.flatten()
            
            if len(embedding) != 512:
                raise EmbeddingError(f"Unexpected embedding dimension: {len(embedding)}")
            
            return embedding.astype(np.float32)
            
        except Exception as e:
            raise EmbeddingError(f"Failed to encode text: {e}") from e
    
    def encode_video_keyframes(self, keyframes: List[Image.Image]) -> Tuple[np.ndarray, List[np.ndarray]]:
        """
        Encode video keyframes and return attention-weighted embedding plus individual frames.
        
        Uses attention-weighted pooling to emphasize important frames, as demonstrated
        in the research notebooks. Falls back to mean pooling if attention fails.
        
        Args:
            keyframes: List of keyframe images
            
        Returns:
            Tuple of (video_embedding, [frame_embeddings])
        """
        if not keyframes:
            raise EmbeddingError("No keyframes provided")
        
        # Encode each keyframe
        frame_embeddings = self.encode_images_batch(keyframes)
        frame_embeddings_array = np.array(frame_embeddings)
        
        # Try attention-weighted pooling (as per notebook research)
        try:
            import torch
            
            # Convert to torch tensors
            frame_emb_tensor = torch.from_numpy(frame_embeddings_array)
            
            # Compute mean embedding for attention baseline
            mean_embedding = frame_emb_tensor.mean(dim=0)
            
            # Attention-weighted pooling (temperature = 0.08 as per notebooks)
            temperature = 0.08
            attention_scores = torch.matmul(
                frame_emb_tensor,
                mean_embedding.unsqueeze(1)
            ).squeeze(1) / temperature
            
            attention_weights = torch.softmax(attention_scores, dim=0)
            
            # Weighted sum
            weighted_embedding = (frame_emb_tensor * attention_weights.unsqueeze(1)).sum(dim=0)
            
            # Convert back to numpy and normalize
            video_embedding = weighted_embedding.numpy().astype(np.float32)
            norm = np.linalg.norm(video_embedding)
            if norm > 0:
                video_embedding = video_embedding / norm
            
            logger.debug(f"Used attention-weighted pooling for {len(keyframes)} frames")
            
        except Exception as e:
            # Fallback to mean pooling if attention fails
            logger.warning(f"Attention-weighted pooling failed, using mean pooling: {e}")
            mean_embedding = np.mean(frame_embeddings_array, axis=0)
            norm = np.linalg.norm(mean_embedding)
            if norm > 0:
                video_embedding = mean_embedding / norm
            else:
                video_embedding = mean_embedding
        
        return video_embedding.astype(np.float32), frame_embeddings
    
    def encode_audio_spectrogram(self, spectrogram_image: Image.Image) -> np.ndarray:
        """
        Encode audio spectrogram as image using CLIP.
        
        Args:
            spectrogram_image: PIL Image of spectrogram
            
        Returns:
            512-dimensional normalized vector
        """
        # Treat spectrogram as image
        return self.encode_image(spectrogram_image)

