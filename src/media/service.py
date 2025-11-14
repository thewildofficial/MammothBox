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
from src.media.vlm_analyzer import VLMAnalyzer, VLMError, VLMMetadata
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
        self.vlm_analyzer = VLMAnalyzer()  # VLM for metadata extraction

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
            self._log_lineage(request_id, asset_id, "processing_start", {
                              "asset_id": str(asset_id)})

            # Retrieve raw file
            file_content = self.storage.retrieve(asset.uri).read()

            # Stage 1: Classification & Normalization
            content_type = asset.content_type or self.processor.detect_mime_type(
                file_content, asset.uri)
            self.processor.validate_file(file_content, content_type)

            processed_data = None
            embedding = None
            frame_embeddings = []

            if content_type.startswith('image/'):
                processed_data = self.processor.process_image(
                    file_content, asset.uri)
                # Stage 2: Embedding
                embedding = self.embedder.encode_image(
                    processed_data.normalized_image)

                # Stage 2.5: VLM Metadata Extraction (if enabled)
                vlm_metadata = None
                if self.settings.vlm_enabled:
                    try:
                        vlm_metadata = self.vlm_analyzer.analyze_image(
                            processed_data.normalized_image)
                        logger.info(
                            f"VLM analysis completed in {vlm_metadata.processing_time_ms:.2f}ms")
                    except VLMError as e:
                        logger.warning(f"VLM analysis failed: {e}")
                    except Exception as e:
                        logger.error(f"Unexpected VLM error: {e}")
                
                # Stage 2.6: OCR Text Detection (if image contains text)
                ocr_result = None
                text_detector = self.processor._get_text_detector()
                ocr_processor = self.processor._get_ocr_processor()
                
                if text_detector and ocr_processor:
                    try:
                        # Save temp file for text detection
                        import tempfile
                        import os
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                            processed_data.normalized_image.save(tmp, format='JPEG')
                            tmp_path = tmp.name
                        
                        try:
                            has_text, text_confidence = text_detector.contains_text(tmp_path)
                            if has_text:
                                logger.info(f"Text detected in image (confidence: {text_confidence:.2f})")
                                ocr_result = ocr_processor.extract_text_from_pil(
                                    processed_data.normalized_image
                                )
                                logger.info(
                                    f"OCR extracted {ocr_result.word_count} words "
                                    f"(avg confidence: {ocr_result.confidence:.2f})"
                                )
                        finally:
                            if os.path.exists(tmp_path):
                                os.unlink(tmp_path)
                    except Exception as e:
                        logger.warning(f"OCR processing failed: {e}")

            elif content_type.startswith('video/'):
                processed_data = self.processor.process_video(
                    file_content, asset.uri)
                # Stage 2: Embedding (mean-pool keyframes)
                # Extract just the images from keyframes (they're already Image objects)
                keyframe_images = processed_data.keyframes
                embedding, frame_embeddings = self.embedder.encode_video_keyframes(
                    keyframe_images
                )

                # Stage 2.5: VLM Metadata Extraction (use first keyframe)
                vlm_metadata = None
                if self.settings.vlm_enabled and keyframe_images:
                    try:
                        vlm_metadata = self.vlm_analyzer.analyze_image(
                            keyframe_images[0])
                        logger.info(
                            f"VLM video analysis completed in {vlm_metadata.processing_time_ms:.2f}ms")
                    except VLMError as e:
                        logger.warning(f"VLM video analysis failed: {e}")
                    except Exception as e:
                        logger.error(f"Unexpected VLM error for video: {e}")

            elif content_type.startswith('audio/'):
                processed_data = self.processor.process_audio(
                    file_content, asset.uri)
                # Stage 2: Embedding (from spectrogram if available)
                if processed_data.waveform_image:
                    embedding = self.embedder.encode_audio_spectrogram(
                        processed_data.waveform_image
                    )
                else:
                    # Fallback: create simple embedding from metadata
                    # In production, might want to use audio-specific model
                    logger.warning(
                        "No waveform image for audio, skipping embedding")
                    embedding = None

            # Stage 3: Deduplication
            sha256 = hashlib.sha256(file_content).hexdigest()
            perceptual_hash = None

            if processed_data and hasattr(processed_data, 'metadata'):
                perceptual_hash = processed_data.metadata.perceptual_hash

            duplicate_id, is_exact = self.deduplicator.check_duplicates(
                sha256, perceptual_hash)

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

            # Stage 4: Clustering (use VLM suggested cluster name if available)
            if embedding is not None:
                suggested_cluster_name = None
                if vlm_metadata and vlm_metadata.suggested_cluster_name:
                    suggested_cluster_name = vlm_metadata.suggested_cluster_name
                    logger.info(
                        f"Using VLM suggested cluster name: {suggested_cluster_name}")

                cluster_id = self.clusterer.assign_to_cluster(
                    embedding, suggested_name=suggested_cluster_name)

                # Stage 5: Storage Finalization
                # Move file to final location
                file_ext = self._get_file_extension(asset.uri)
                final_uri = self.storage.store_media(
                    cluster_id, asset_id, BytesIO(
                        file_content), f"{asset_id}{file_ext}"
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
                        timestamp = (duration / len(frame_embeddings)) * \
                            idx if len(frame_embeddings) > 0 else 0
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

                # Store metadata (including VLM metadata)
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

                # Add VLM metadata if available
                if vlm_metadata:
                    metadata.update({
                        "vlm_primary_category": vlm_metadata.primary_category,
                        "vlm_tags": vlm_metadata.tags,
                        "vlm_description": vlm_metadata.description,
                        "vlm_detected_objects": vlm_metadata.detected_objects,
                        "vlm_scene_type": vlm_metadata.scene_type,
                        "vlm_color_palette": vlm_metadata.color_palette,
                        "vlm_model": vlm_metadata.vlm_model,
                        "vlm_fallback_used": vlm_metadata.fallback_used,
                        "vlm_processing_time_ms": vlm_metadata.processing_time_ms
                    })
                
                # Add OCR metadata if text was detected
                if ocr_result:
                    metadata.update({
                        "ocr_text": ocr_result.text,
                        "ocr_confidence": ocr_result.confidence,
                        "ocr_word_count": ocr_result.word_count,
                        "ocr_bounding_boxes": [
                            {
                                "word": bbox.word,
                                "x": bbox.x,
                                "y": bbox.y,
                                "width": bbox.width,
                                "height": bbox.height,
                                "confidence": bbox.confidence
                            }
                            for bbox in ocr_result.bounding_boxes
                        ],
                        "contains_text": True
                    })

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
            logger.error(
                f"Unexpected error processing asset {asset_id}: {e}", exc_info=True)
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

    def label_cluster_with_vlm(
        self,
        cluster_id: UUID,
        max_images: int = 5
    ) -> Dict[str, Any]:
        """
        Label cluster using VLM by analyzing representative images.

        Efficient cluster-first approach from notebooks:
        - Analyzes multiple representative images from cluster
        - Generates human-readable cluster name
        - Much more efficient than per-image labeling

        Args:
            cluster_id: Cluster to label
            max_images: Maximum representative images to analyze

        Returns:
            Dictionary with cluster metadata
        """
        # Get cluster
        cluster = self.db.query(Cluster).filter(
            Cluster.id == cluster_id).first()
        if not cluster:
            raise MediaServiceError(f"Cluster {cluster_id} not found")

        # Get representative assets (images only for VLM analysis)
        assets = self.db.query(Asset).filter(
            Asset.cluster_id == cluster_id,
            Asset.content_type.like('image/%'),
            Asset.status == 'done'
        ).limit(max_images).all()

        if not assets:
            logger.warning(
                f"No images found in cluster {cluster_id} for VLM labeling")
            return {
                "cluster_id": str(cluster_id),
                "cluster_name": cluster.name,
                "labeled": False,
                "reason": "no_images"
            }

        # Load representative images
        from PIL import Image
        images = []
        for asset in assets:
            try:
                file_content = self.storage.retrieve(asset.uri).read()
                image = Image.open(BytesIO(file_content))
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                images.append(image)
            except Exception as e:
                logger.warning(f"Failed to load image {asset.id}: {e}")
                continue

        if not images:
            return {
                "cluster_id": str(cluster_id),
                "cluster_name": cluster.name,
                "labeled": False,
                "reason": "failed_to_load_images"
            }

        # Use VLM to label cluster
        try:
            # Extract cluster ID integer for display
            cluster_num = str(cluster_id)[-8:]  # Last 8 chars of UUID
            cluster_metadata = self.vlm_analyzer.label_cluster(
                images, cluster_num, max_images
            )

            # Update cluster with VLM-generated name
            old_name = cluster.name
            cluster.name = cluster_metadata.cluster_name
            cluster.metadata = cluster.metadata or {}
            cluster.metadata.update({
                "vlm_description": cluster_metadata.description,
                "vlm_tags": cluster_metadata.tags,
                "vlm_primary_category": cluster_metadata.primary_category,
                "vlm_model": cluster_metadata.vlm_model,
                "images_analyzed": cluster_metadata.images_analyzed,
                "total_images": cluster_metadata.total_images
            })
            self.db.commit()

            logger.info(
                f"Labeled cluster {cluster_id}: '{old_name}' -> '{cluster.name}' "
                f"(analyzed {cluster_metadata.images_analyzed} of {cluster_metadata.total_images} images)"
            )

            return {
                "cluster_id": str(cluster_id),
                "old_name": old_name,
                "new_name": cluster.name,
                "description": cluster_metadata.description,
                "tags": cluster_metadata.tags,
                "labeled": True,
                "images_analyzed": cluster_metadata.images_analyzed
            }

        except VLMError as e:
            logger.error(f"VLM cluster labeling failed for {cluster_id}: {e}")
            return {
                "cluster_id": str(cluster_id),
                "cluster_name": cluster.name,
                "labeled": False,
                "reason": "vlm_error",
                "error": str(e)
            }

    def batch_label_clusters(
        self,
        min_images: int = 3,
        max_clusters: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Batch label multiple clusters using VLM.

        Useful for labeling provisional clusters after ingest.

        Args:
            min_images: Minimum images required to label cluster
            max_clusters: Maximum clusters to label (None = all)

        Returns:
            List of labeling results
        """
        # Find clusters that need labeling (provisional or generic names)
        from sqlalchemy import func

        clusters_query = self.db.query(
            Cluster.id,
            func.count(Asset.id).label('asset_count')
        ).outerjoin(
            Asset, Asset.cluster_id == Cluster.id
        ).filter(
            Asset.status == 'done'
        ).group_by(
            Cluster.id
        ).having(
            func.count(Asset.id) >= min_images
        )

        if max_clusters:
            clusters_query = clusters_query.limit(max_clusters)

        cluster_candidates = clusters_query.all()

        logger.info(
            f"Found {len(cluster_candidates)} clusters with >= {min_images} images for VLM labeling")

        results = []
        for cluster_id, asset_count in cluster_candidates:
            try:
                result = self.label_cluster_with_vlm(cluster_id)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to label cluster {cluster_id}: {e}")
                results.append({
                    "cluster_id": str(cluster_id),
                    "labeled": False,
                    "reason": "exception",
                    "error": str(e)
                })

        return results

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
