"""
Media processing service orchestrator.

Coordinates all stages of media processing: normalization, embedding,
deduplication, clustering, and storage finalization.
"""

import hashlib
import logging
from io import BytesIO
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.catalog.models import Asset, VideoFrame, Lineage, Cluster
from src.config.settings import get_settings
from src.media.processor import MediaProcessor, MediaProcessingError
from src.media.embedder import MediaEmbedder, EmbeddingError
from src.media.deduplicator import MediaDeduplicator
from src.media.clusterer import MediaClusterer
from src.storage.adapter import StorageAdapter

logger = logging.getLogger(__name__)


class MediaServiceError(Exception):
    """Exception raised during media processing service operations."""
    pass


class MediaService:
    """
    Main service for processing media files through the complete pipeline.
    
    Orchestrates all stages: normalization, embedding, deduplication,
    clustering, and storage finalization.
    """
    
    def __init__(self, db: Session, storage: StorageAdapter):
        """
        Initialize media service.
        
        Args:
            db: Database session
            storage: Storage adapter
        """
        self.db = db
        self.storage = storage
        self.settings = get_settings()
        self.processor = MediaProcessor(storage)
        self.embedder = MediaEmbedder()
        self.deduplicator = MediaDeduplicator(db)
        self.clusterer = MediaClusterer(db)
    
    def process_asset(self, asset_id: UUID, request_id: str) -> Dict[str, Any]:
        """
        Process a single media asset through the complete pipeline.
        
        Args:
            asset_id: Asset ID to process
            request_id: Request ID for lineage tracking
            
        Returns:
            Dictionary with processing results
        """
        # Load asset
        asset = self.db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            raise MediaServiceError(f"Asset {asset_id} not found")
        
        try:
            # Update status to processing
            asset.status = "processing"
            self.db.commit()
            
            # Log start
            self._log_lineage(request_id, asset_id, "processing_start", {"asset_id": str(asset_id)})
            
            # Retrieve raw file
            file_content = self.storage.retrieve(asset.uri).read()
            
            # Stage 1: Classification & Normalization
            content_type = asset.content_type or self.processor.detect_mime_type(file_content, asset.uri)
            self.processor.validate_file(file_content, content_type)
            
            processed_data = None
            embedding = None
            frame_embeddings = []
            
            if content_type.startswith('image/'):
                processed_data = self.processor.process_image(file_content, asset.uri)
                # Stage 2: Embedding
                embedding = self.embedder.encode_image(processed_data.normalized_image)
                
            elif content_type.startswith('video/'):
                processed_data = self.processor.process_video(file_content, asset.uri)
                # Stage 2: Embedding (mean-pool keyframes)
                # Extract just the images from keyframes (they're already Image objects)
                keyframe_images = processed_data.keyframes
                embedding, frame_embeddings = self.embedder.encode_video_keyframes(
                    keyframe_images
                )
                
            elif content_type.startswith('audio/'):
                processed_data = self.processor.process_audio(file_content, asset.uri)
                # Stage 2: Embedding (from spectrogram if available)
                if processed_data.waveform_image:
                    embedding = self.embedder.encode_audio_spectrogram(
                        processed_data.waveform_image
                    )
                else:
                    # Fallback: create simple embedding from metadata
                    # In production, might want to use audio-specific model
                    logger.warning("No waveform image for audio, skipping embedding")
                    embedding = None
            
            # Stage 3: Deduplication
            sha256 = hashlib.sha256(file_content).hexdigest()
            perceptual_hash = None
            
            if processed_data and hasattr(processed_data, 'metadata'):
                perceptual_hash = processed_data.metadata.perceptual_hash
            
            duplicate_id, is_exact = self.deduplicator.check_duplicates(sha256, perceptual_hash)
            
            if duplicate_id:
                # Link to existing asset
                asset.sha256 = sha256
                asset.status = "done"
                asset.cluster_id = self.db.query(Asset).filter(
                    Asset.id == duplicate_id
                ).first().cluster_id
                self.db.commit()
                
                self._log_lineage(
                    request_id, asset_id, "deduplication",
                    {"duplicate_of": str(duplicate_id), "is_exact": is_exact}
                )
                
                return {
                    "success": True,
                    "asset_id": str(asset_id),
                    "duplicate": True,
                    "duplicate_of": str(duplicate_id),
                    "cluster_id": str(asset.cluster_id) if asset.cluster_id else None
                }
            
            # Stage 4: Clustering
            if embedding is not None:
                cluster_id = self.clusterer.assign_to_cluster(embedding)
                
                # Stage 5: Storage Finalization
                # Move file to final location
                file_ext = self._get_file_extension(asset.uri)
                final_uri = self.storage.store_media(
                    cluster_id, asset_id, BytesIO(file_content), f"{asset_id}{file_ext}"
                )
                
                # Store thumbnail
                if processed_data and hasattr(processed_data, 'thumbnail'):
                    thumb_uri = self.storage.store_derived(
                        cluster_id, asset_id,
                        self._image_to_bytesio(processed_data.thumbnail),
                        "thumb.jpg"
                    )
                else:
                    thumb_uri = None
                
                # Store video frame embeddings
                if frame_embeddings and hasattr(processed_data, 'keyframes'):
                    # Note: keyframes are Image objects, timestamps are in metadata
                    for idx, frame_emb in enumerate(frame_embeddings):
                        # Calculate timestamp from duration and frame index
                        duration = processed_data.metadata.duration or 0
                        timestamp = (duration / len(frame_embeddings)) * idx if len(frame_embeddings) > 0 else 0
                        video_frame = VideoFrame(
                            asset_id=asset_id,
                            frame_idx=idx,
                            timestamp_ms=int(timestamp * 1000),
                            embedding=frame_emb.tolist()
                        )
                        self.db.add(video_frame)
                
                # Update asset record
                asset.uri = final_uri
                asset.sha256 = sha256
                asset.embedding = embedding.tolist()
                asset.cluster_id = cluster_id
                asset.status = "done"
                
                # Store metadata
                metadata = {}
                if processed_data and hasattr(processed_data, 'metadata'):
                    metadata = {
                        "width": processed_data.metadata.width,
                        "height": processed_data.metadata.height,
                        "duration": processed_data.metadata.duration,
                        "codec": processed_data.metadata.codec,
                        "bitrate": processed_data.metadata.bitrate,
                        "perceptual_hash": processed_data.metadata.perceptual_hash,
                        "exif": processed_data.metadata.exif
                    }
                
                asset.metadata = metadata
                self.db.commit()
                
                self._log_lineage(
                    request_id, asset_id, "processing_complete",
                    {
                        "cluster_id": str(cluster_id),
                        "final_uri": final_uri,
                        "thumbnail_uri": thumb_uri
                    }
                )
                
                return {
                    "success": True,
                    "asset_id": str(asset_id),
                    "cluster_id": str(cluster_id),
                    "duplicate": False
                }
            else:
                # No embedding generated (e.g., audio without waveform)
                asset.status = "failed"
                self.db.commit()
                raise MediaServiceError("Failed to generate embedding")
                
        except (MediaProcessingError, EmbeddingError) as e:
            logger.error(f"Media processing error for asset {asset_id}: {e}")
            asset.status = "failed"
            self.db.commit()
            self._log_lineage(
                request_id, asset_id, "processing_error",
                {"error": str(e)}, success=False, error_message=str(e)
            )
            raise MediaServiceError(f"Processing failed: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error processing asset {asset_id}: {e}", exc_info=True)
            asset.status = "failed"
            self.db.commit()
            self._log_lineage(
                request_id, asset_id, "processing_error",
                {"error": str(e)}, success=False, error_message=str(e)
            )
            raise MediaServiceError(f"Unexpected error: {e}") from e
    
    def _get_file_extension(self, uri: str) -> str:
        """Extract file extension from URI."""
        from pathlib import Path
        return Path(uri).suffix or ".bin"
    
    def _image_to_bytesio(self, image) -> BytesIO:
        """Convert PIL Image to BytesIO."""
        buffer = BytesIO()
        image.save(buffer, format='JPEG', quality=90)
        buffer.seek(0)
        return buffer
    
    def _log_lineage(
        self,
        request_id: str,
        asset_id: UUID,
        stage: str,
        detail: Dict[str, Any],
        success: bool = True,
        error_message: Optional[str] = None
    ) -> None:
        """Log lineage entry."""
        lineage = Lineage(
            request_id=request_id,
            asset_id=asset_id,
            stage=stage,
            detail=detail,
            success=success,
            error_message=error_message
        )
        self.db.add(lineage)
        self.db.commit()

