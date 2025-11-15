"""Deduplication module for detecting exact and near-duplicate media files."""

import hashlib
import logging
from typing import Optional, Tuple
from uuid import UUID

import imagehash
from sqlalchemy.orm import Session

from src.catalog.models import Asset

logger = logging.getLogger(__name__)


class DeduplicationError(Exception):
    pass


class MediaDeduplicator:
    """Deduplicator for media files."""

    # Hamming distance threshold for near-duplicates
    NEAR_DUPLICATE_THRESHOLD = 5

    def __init__(self, db: Session):
        self.db = db

    def compute_sha256(self, file_content: bytes) -> str:
        return hashlib.sha256(file_content).hexdigest()

    def compute_perceptual_hash(self, image_data) -> str:
        from PIL import Image
        from io import BytesIO

        if isinstance(image_data, bytes):
            image = Image.open(BytesIO(image_data))
        else:
            image = image_data

        phash = imagehash.phash(image)
        return str(phash)

    def hamming_distance(self, hash1: str, hash2: str) -> int:
        try:
            h1 = imagehash.hex_to_hash(hash1)
            h2 = imagehash.hex_to_hash(hash2)
            return h1 - h2
        except Exception as e:
            logger.warning(f"Failed to compute Hamming distance: {e}")
            return float('inf')

    def check_exact_duplicate(self, sha256: str) -> Optional[UUID]:
        """
        Check for exact duplicate by SHA256 hash.

        Args:
            sha256: SHA256 hash

        Returns:
            Asset ID of duplicate if found, None otherwise
        """
        existing = self.db.query(Asset).filter(
            Asset.sha256 == sha256,
            Asset.kind == 'media',
            Asset.status == 'done'
        ).first()

        if existing:
            logger.info(
                f"Found exact duplicate: {existing.id} (SHA256: {sha256[:16]}...)")
            return existing.id

        return None

    def check_near_duplicate(self, perceptual_hash: str) -> Optional[UUID]:
        """
        Check for near-duplicate by perceptual hash.

        Args:
            perceptual_hash: Perceptual hash string

        Returns:
            Asset ID of near-duplicate if found, None otherwise
        """
        # Query all media assets with perceptual hashes
        # Note: This is stored in metadata JSONB, so we need to query differently
        # For now, we'll check all done media assets and compare hashes
        # In production, consider adding a dedicated column or GIN index

        existing_assets = self.db.query(Asset).filter(
            Asset.kind == 'media',
            Asset.status == 'done',
            Asset.asset_metadata.isnot(None)
        ).all()

        for asset in existing_assets:
            if asset.asset_metadata and 'perceptual_hash' in asset.asset_metadata:
                existing_hash = asset.asset_metadata['perceptual_hash']
                distance = self.hamming_distance(
                    perceptual_hash, existing_hash)

                if distance < self.NEAR_DUPLICATE_THRESHOLD:
                    logger.info(
                        f"Found near-duplicate: {asset.id} "
                        f"(Hamming distance: {distance})"
                    )
                    return asset.id

        return None

    def check_duplicates(
        self,
        sha256: str,
        perceptual_hash: Optional[str] = None
    ) -> Tuple[Optional[UUID], bool]:
        """
        Check for both exact and near-duplicates.

        Args:
            sha256: SHA256 hash
            perceptual_hash: Optional perceptual hash

        Returns:
            Tuple of (duplicate_asset_id, is_exact_duplicate)
        """
        # Check exact duplicate first
        exact_dup = self.check_exact_duplicate(sha256)
        if exact_dup:
            return exact_dup, True

        # Check near-duplicate if perceptual hash provided
        if perceptual_hash:
            near_dup = self.check_near_duplicate(perceptual_hash)
            if near_dup:
                return near_dup, False

        return None, False
