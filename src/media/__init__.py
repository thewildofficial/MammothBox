"""
Media processing module.

Provides media processing pipeline components: processor, embedder,
deduplicator, clusterer, and service orchestrator.
"""

from src.media.processor import (
    MediaProcessor,
    MediaProcessingError,
    MediaMetadata,
    ProcessedImage,
    ProcessedVideo,
    ProcessedAudio,
)
from src.media.embedder import MediaEmbedder, EmbeddingError
from src.media.deduplicator import MediaDeduplicator, DeduplicationError
from src.media.clusterer import MediaClusterer, ClusteringError
from src.media.service import MediaService, MediaServiceError

__all__ = [
    "MediaProcessor",
    "MediaProcessingError",
    "MediaMetadata",
    "ProcessedImage",
    "ProcessedVideo",
    "ProcessedAudio",
    "MediaEmbedder",
    "EmbeddingError",
    "MediaDeduplicator",
    "DeduplicationError",
    "MediaClusterer",
    "ClusteringError",
    "MediaService",
    "MediaServiceError",
]

