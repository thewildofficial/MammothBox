"""Clustering module for assigning media files to clusters."""

import logging
from typing import Optional, Tuple
from uuid import UUID, uuid4
import numpy as np

from sqlalchemy.orm import Session
from sqlalchemy import text

from src.catalog.models import Cluster
from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class ClusteringError(Exception):
    pass


class MediaClusterer:
    """Clusterer for media files based on CLIP embeddings."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.default_threshold = self.settings.cluster_threshold

    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        # Both vectors should be normalized, so dot product = cosine similarity
        dot_product = np.dot(vec1, vec2)
        return float(dot_product)

    def find_best_cluster(
        self,
        embedding: np.ndarray,
        threshold: Optional[float] = None
    ) -> Optional[Tuple[UUID, float]]:
        """Find best matching cluster for embedding."""
        if threshold is None:
            threshold = self.default_threshold

        # Query all non-provisional clusters first, then provisional
        clusters = self.db.query(Cluster).filter(
            Cluster.centroid.isnot(None)
        ).all()

        best_cluster_id = None
        best_similarity = -1.0

        for cluster in clusters:
            if cluster.centroid is None:
                continue

            # Convert centroid to numpy array
            centroid = np.array(cluster.centroid, dtype=np.float32)

            # Compute cosine similarity
            similarity = self.cosine_similarity(embedding, centroid)

            # Use cluster-specific threshold if available, else default
            cluster_threshold = cluster.threshold if cluster.threshold else threshold

            if similarity >= cluster_threshold and similarity > best_similarity:
                best_similarity = similarity
                best_cluster_id = cluster.id

        if best_cluster_id:
            logger.info(
                f"Found matching cluster: {best_cluster_id} "
                f"(similarity: {best_similarity:.3f})"
            )
            return best_cluster_id, best_similarity

        return None

    def update_cluster_centroid(
        self,
        cluster_id: UUID,
        new_embedding: np.ndarray
    ) -> None:
        """
        Update cluster centroid incrementally.

        Args:
            cluster_id: Cluster ID
            new_embedding: New embedding to incorporate
        """
        cluster = self.db.query(Cluster).filter(
            Cluster.id == cluster_id).first()
        if not cluster:
            raise ClusteringError(f"Cluster {cluster_id} not found")

        if cluster.centroid is None:
            # First embedding, use as-is
            cluster.centroid = new_embedding.tolist()
        else:
            # Get current centroid and count of assets
            current_centroid = np.array(cluster.centroid, dtype=np.float32)

            # Count assets in cluster
            from src.catalog.models import Asset
            asset_count = self.db.query(Asset).filter(
                Asset.cluster_id == cluster_id
            ).count()

            # Incremental update: weighted average
            # new_centroid = (old_centroid * n + new_embedding) / (n + 1)
            new_centroid = (current_centroid * asset_count +
                            new_embedding) / (asset_count + 1)

            # Re-normalize
            norm = np.linalg.norm(new_centroid)
            if norm > 0:
                new_centroid = new_centroid / norm

            cluster.centroid = new_centroid.tolist()

        from datetime import datetime
        cluster.updated_at = datetime.utcnow()
        self.db.commit()

    def create_cluster(
        self,
        embedding: np.ndarray,
        name: Optional[str] = None,
        threshold: Optional[float] = None
    ) -> UUID:
        """
        Create a new provisional cluster.

        Args:
            embedding: Initial embedding vector
            name: Optional cluster name (defaults to generated name)
            threshold: Similarity threshold (defaults to default_threshold)

        Returns:
            New cluster ID
        """
        if threshold is None:
            threshold = self.default_threshold

        if name is None:
            # Generate unique name
            base_name = f"Cluster {uuid4().hex[:8]}"
            name = base_name
        else:
            base_name = name

        # Ensure name is unique
        counter = 1
        while self.db.query(Cluster).filter(Cluster.name == name).first():
            name = f"{base_name}_{counter}"
            counter += 1

        # Ensure embedding is normalized
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        cluster = Cluster(
            id=uuid4(),
            name=name,
            centroid=embedding.tolist(),
            threshold=threshold,
            provisional=True
        )

        self.db.add(cluster)
        self.db.commit()

        logger.info(f"Created new provisional cluster: {cluster.id} ({name})")
        return cluster.id

    def assign_to_cluster(
        self,
        embedding: np.ndarray,
        suggested_name: Optional[str] = None
    ) -> UUID:
        """
        Assign embedding to existing cluster or create new one.

        Args:
            embedding: Embedding vector
            suggested_name: Optional name for new cluster

        Returns:
            Cluster ID
        """
        # Find best matching cluster
        match = self.find_best_cluster(embedding)

        if match:
            cluster_id, similarity = match
            # Update centroid
            self.update_cluster_centroid(cluster_id, embedding)
            return cluster_id
        else:
            # Create new cluster
            return self.create_cluster(embedding, name=suggested_name)
