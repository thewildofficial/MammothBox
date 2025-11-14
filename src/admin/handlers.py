"""
Admin operations handlers for schema and cluster management.

Provides business logic for:
- Schema proposal review and approval
- Cluster management (rename, merge, threshold adjustment)
- Statistics and analytics
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID
from datetime import datetime

import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.catalog.models import Asset, Cluster, SchemaDef, Lineage
from src.ingest.json_processor import JsonProcessor, JsonProcessingError

logger = logging.getLogger(__name__)


class AdminError(Exception):
    """Exception raised during admin operations."""
    pass


class AdminHandlers:
    """
    Admin operations for schema and cluster management.

    Handles human-in-the-loop workflows for reviewing schema proposals
    and managing media clusters.
    """

    def __init__(self, db: Session):
        """
        Initialize admin handlers.

        Args:
            db: Database session
        """
        self.db = db
        self.json_processor = JsonProcessor(db)

    # ==================== Schema Management ====================

    def list_schemas(
        self,
        status: Optional[str] = None,
        storage_choice: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List all schema proposals with filtering.

        Args:
            status: Filter by status (provisional, active, rejected)
            storage_choice: Filter by storage choice (sql, jsonb)

        Returns:
            List of schema dictionaries with sample counts
        """
        query = self.db.query(SchemaDef)

        if status:
            query = query.filter(SchemaDef.status == status)
        if storage_choice:
            query = query.filter(SchemaDef.storage_choice == storage_choice)

        schemas = query.order_by(SchemaDef.created_at.desc()).all()

        results = []
        for schema in schemas:
            # Count assets using this schema
            asset_count = self.db.query(Asset).filter(
                Asset.schema_id == schema.id
            ).count()

            results.append({
                "id": str(schema.id),
                "name": schema.name,
                "storage_choice": schema.storage_choice,
                "status": schema.status,
                "ddl": schema.ddl,
                "sample_size": schema.sample_size,
                "asset_count": asset_count,
                "field_stability": schema.field_stability,
                "max_depth": schema.max_depth,
                "top_level_keys": schema.top_level_keys,
                "decision_reason": schema.decision_reason,
                "created_at": schema.created_at.isoformat(),
                "reviewed_by": schema.reviewed_by,
                "reviewed_at": schema.reviewed_at.isoformat() if schema.reviewed_at else None
            })

        return results

    def get_schema(self, schema_id: UUID) -> Dict[str, Any]:
        """
        Get detailed schema information.

        Args:
            schema_id: Schema ID

        Returns:
            Schema dictionary with full details
        """
        schema = self.db.query(SchemaDef).filter(
            SchemaDef.id == schema_id
        ).first()

        if not schema:
            raise AdminError(f"Schema {schema_id} not found")

        asset_count = self.db.query(Asset).filter(
            Asset.schema_id == schema.id
        ).count()

        return {
            "id": str(schema.id),
            "name": schema.name,
            "structure_hash": schema.structure_hash,
            "storage_choice": schema.storage_choice,
            "status": schema.status,
            "version": schema.version,
            "ddl": schema.ddl,
            "sample_size": schema.sample_size,
            "asset_count": asset_count,
            "field_stability": schema.field_stability,
            "max_depth": schema.max_depth,
            "top_level_keys": schema.top_level_keys,
            "decision_reason": schema.decision_reason,
            "created_at": schema.created_at.isoformat(),
            "updated_at": schema.updated_at.isoformat(),
            "reviewed_by": schema.reviewed_by,
            "reviewed_at": schema.reviewed_at.isoformat() if schema.reviewed_at else None
        }

    def approve_schema(
        self,
        schema_id: UUID,
        reviewed_by: str,
        table_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Approve a provisional schema and execute DDL migration.

        Args:
            schema_id: Schema ID to approve
            reviewed_by: Admin identifier
            table_name: Optional custom table name

        Returns:
            Updated schema details
        """
        try:
            # Use JsonProcessor's existing approve logic
            schema = self.json_processor.approve_schema(schema_id, reviewed_by)

            # Log admin action
            self._log_admin_action(
                action="schema_approved",
                target_type="schema",
                target_id=schema_id,
                performed_by=reviewed_by,
                details={"schema_name": schema.name,
                         "storage_choice": schema.storage_choice}
            )

            return self.get_schema(schema_id)

        except JsonProcessingError as e:
            raise AdminError(str(e)) from e

    def reject_schema(
        self,
        schema_id: UUID,
        reviewed_by: str,
        reason: str
    ) -> Dict[str, Any]:
        """
        Reject a provisional schema.

        Args:
            schema_id: Schema ID to reject
            reviewed_by: Admin identifier
            reason: Rejection reason

        Returns:
            Updated schema details
        """
        try:
            # Use JsonProcessor's existing reject logic
            schema = self.json_processor.reject_schema(
                schema_id, reviewed_by, reason)

            # Log admin action
            self._log_admin_action(
                action="schema_rejected",
                target_type="schema",
                target_id=schema_id,
                performed_by=reviewed_by,
                details={"schema_name": schema.name, "reason": reason}
            )

            return self.get_schema(schema_id)

        except JsonProcessingError as e:
            raise AdminError(str(e)) from e

    # ==================== Cluster Management ====================

    def list_clusters(
        self,
        provisional_only: bool = False,
        min_assets: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        List all clusters with statistics.

        Args:
            provisional_only: Only return provisional clusters
            min_assets: Minimum asset count filter

        Returns:
            List of cluster dictionaries with statistics
        """
        query = self.db.query(
            Cluster,
            func.count(Asset.id).label('asset_count')
        ).outerjoin(
            Asset, Asset.cluster_id == Cluster.id
        ).group_by(Cluster.id)

        if provisional_only:
            query = query.filter(Cluster.provisional.is_(True))

        if min_assets is not None:
            query = query.having(func.count(Asset.id) >= min_assets)

        query = query.order_by(Cluster.created_at.desc())

        results = []
        for cluster, asset_count in query.all():
            results.append({
                "id": str(cluster.id),
                "name": cluster.name,
                "asset_count": asset_count,
                "threshold": cluster.threshold,
                "provisional": cluster.provisional,
                "metadata": cluster.cluster_metadata,
                "created_at": cluster.created_at.isoformat(),
                "updated_at": cluster.updated_at.isoformat()
            })

        return results

    def get_cluster(self, cluster_id: UUID) -> Dict[str, Any]:
        """
        Get detailed cluster information with statistics.

        Args:
            cluster_id: Cluster ID

        Returns:
            Cluster dictionary with full details and statistics
        """
        cluster = self.db.query(Cluster).filter(
            Cluster.id == cluster_id
        ).first()

        if not cluster:
            raise AdminError(f"Cluster {cluster_id} not found")

        # Get asset count
        asset_count = self.db.query(Asset).filter(
            Asset.cluster_id == cluster_id
        ).count()

        # Get assets for statistics
        assets = self.db.query(Asset).filter(
            Asset.cluster_id == cluster_id,
            Asset.embedding.isnot(None)
        ).all()

        # Compute centroid quality (avg similarity to centroid)
        centroid_quality = None
        if cluster.centroid and assets:
            centroid_vec = np.array(cluster.centroid, dtype=np.float32)
            similarities = []
            for asset in assets:
                if asset.embedding:
                    asset_vec = np.array(asset.embedding, dtype=np.float32)
                    sim = float(np.dot(centroid_vec, asset_vec))
                    similarities.append(sim)

            if similarities:
                centroid_quality = {
                    "mean": float(np.mean(similarities)),
                    "std": float(np.std(similarities)),
                    "min": float(np.min(similarities)),
                    "max": float(np.max(similarities))
                }

        return {
            "id": str(cluster.id),
            "name": cluster.name,
            "asset_count": asset_count,
            "threshold": cluster.threshold,
            "provisional": cluster.provisional,
            "centroid_quality": centroid_quality,
            "metadata": cluster.cluster_metadata,
            "created_at": cluster.created_at.isoformat(),
            "updated_at": cluster.updated_at.isoformat()
        }

    def rename_cluster(
        self,
        cluster_id: UUID,
        new_name: str,
        performed_by: str
    ) -> Dict[str, Any]:
        """
        Rename a cluster.

        Args:
            cluster_id: Cluster ID
            new_name: New cluster name
            performed_by: Admin identifier

        Returns:
            Updated cluster details
        """
        cluster = self.db.query(Cluster).filter(
            Cluster.id == cluster_id
        ).first()

        if not cluster:
            raise AdminError(f"Cluster {cluster_id} not found")

        # Check for name collision
        existing = self.db.query(Cluster).filter(
            Cluster.name == new_name,
            Cluster.id != cluster_id
        ).first()

        if existing:
            raise AdminError(f"Cluster name '{new_name}' already exists")

        old_name = cluster.name
        cluster.name = new_name
        cluster.updated_at = datetime.utcnow()

        self.db.commit()

        # Log admin action
        self._log_admin_action(
            action="cluster_renamed",
            target_type="cluster",
            target_id=cluster_id,
            performed_by=performed_by,
            details={"old_name": old_name, "new_name": new_name}
        )

        logger.info(
            f"Renamed cluster {cluster_id}: '{old_name}' -> '{new_name}'")

        return self.get_cluster(cluster_id)

    def merge_clusters(
        self,
        source_cluster_ids: List[UUID],
        target_cluster_id: UUID,
        performed_by: str
    ) -> Dict[str, Any]:
        """
        Merge multiple clusters into a target cluster.

        Updates all assets to target cluster, recomputes centroid,
        and deletes source clusters.

        Args:
            source_cluster_ids: List of source cluster IDs to merge
            target_cluster_id: Target cluster ID
            performed_by: Admin identifier

        Returns:
            Updated target cluster details
        """
        # Validate target cluster exists
        target = self.db.query(Cluster).filter(
            Cluster.id == target_cluster_id
        ).first()

        if not target:
            raise AdminError(f"Target cluster {target_cluster_id} not found")

        # Validate source clusters exist and collect them
        source_clusters = self.db.query(Cluster).filter(
            Cluster.id.in_(source_cluster_ids)
        ).all()

        if len(source_clusters) != len(source_cluster_ids):
            raise AdminError("One or more source clusters not found")

        # Cannot merge cluster into itself
        if target_cluster_id in source_cluster_ids:
            raise AdminError("Cannot merge cluster into itself")

        # Collect all embeddings for centroid recomputation
        all_embeddings = []
        total_assets_moved = 0

        try:
            # Move assets from source clusters to target
            for source in source_clusters:
                assets = self.db.query(Asset).filter(
                    Asset.cluster_id == source.id
                ).all()

                for asset in assets:
                    asset.cluster_id = target_cluster_id
                    if asset.embedding:
                        all_embeddings.append(
                            np.array(asset.embedding, dtype=np.float32))

                total_assets_moved += len(assets)

                # Delete source cluster
                self.db.delete(source)

            # Recompute target centroid from all embeddings
            if all_embeddings:
                centroid = np.mean(all_embeddings, axis=0)
                # Normalize
                norm = np.linalg.norm(centroid)
                if norm > 0:
                    centroid = centroid / norm
                target.centroid = centroid.tolist()

            target.updated_at = datetime.utcnow()

            self.db.commit()

            # Log admin action
            self._log_admin_action(
                action="clusters_merged",
                target_type="cluster",
                target_id=target_cluster_id,
                performed_by=performed_by,
                details={
                    "source_cluster_ids": [str(cid) for cid in source_cluster_ids],
                    "assets_moved": total_assets_moved,
                    "source_cluster_names": [c.name for c in source_clusters]
                }
            )

            logger.info(
                f"Merged {len(source_clusters)} clusters into {target.name}: "
                f"moved {total_assets_moved} assets"
            )

            return self.get_cluster(target_cluster_id)

        except Exception as e:
            self.db.rollback()
            raise AdminError(f"Failed to merge clusters: {e}") from e

    def update_cluster_threshold(
        self,
        cluster_id: UUID,
        threshold: float,
        performed_by: str,
        re_evaluate: bool = False
    ) -> Dict[str, Any]:
        """
        Update cluster similarity threshold.

        Args:
            cluster_id: Cluster ID
            threshold: New threshold value (0.0 to 1.0)
            performed_by: Admin identifier
            re_evaluate: If True, re-evaluate cluster assignments

        Returns:
            Updated cluster details
        """
        if not 0.0 <= threshold <= 1.0:
            raise AdminError("Threshold must be between 0.0 and 1.0")

        cluster = self.db.query(Cluster).filter(
            Cluster.id == cluster_id
        ).first()

        if not cluster:
            raise AdminError(f"Cluster {cluster_id} not found")

        old_threshold = cluster.threshold
        cluster.threshold = threshold
        cluster.updated_at = datetime.utcnow()

        self.db.commit()

        # Log admin action
        self._log_admin_action(
            action="cluster_threshold_updated",
            target_type="cluster",
            target_id=cluster_id,
            performed_by=performed_by,
            details={
                "old_threshold": old_threshold,
                "new_threshold": threshold,
                "re_evaluate": re_evaluate
            }
        )

        logger.info(
            f"Updated threshold for cluster {cluster.name}: "
            f"{old_threshold} -> {threshold}"
        )

        if re_evaluate:
            logger.warning(
                "Threshold updated with re-evaluation requested, "
                "but automatic re-clustering not yet implemented"
            )

        return self.get_cluster(cluster_id)

    def confirm_cluster(
        self,
        cluster_id: UUID,
        performed_by: str
    ) -> Dict[str, Any]:
        """
        Mark cluster as confirmed (non-provisional).

        Args:
            cluster_id: Cluster ID
            performed_by: Admin identifier

        Returns:
            Updated cluster details
        """
        cluster = self.db.query(Cluster).filter(
            Cluster.id == cluster_id
        ).first()

        if not cluster:
            raise AdminError(f"Cluster {cluster_id} not found")

        if not cluster.provisional:
            raise AdminError(f"Cluster {cluster.name} is already confirmed")

        cluster.provisional = False
        cluster.updated_at = datetime.utcnow()

        self.db.commit()

        # Log admin action
        self._log_admin_action(
            action="cluster_confirmed",
            target_type="cluster",
            target_id=cluster_id,
            performed_by=performed_by,
            details={"cluster_name": cluster.name}
        )

        logger.info(f"Confirmed cluster {cluster.name}")

        return self.get_cluster(cluster_id)

    # ==================== Statistics & Analytics ====================

    def get_pending_schemas(self) -> List[Dict[str, Any]]:
        """Get all provisional schemas awaiting review."""
        return self.list_schemas(status="provisional")

    def get_cluster_statistics(self) -> Dict[str, Any]:
        """
        Get overall cluster statistics.

        Returns:
            Dictionary with cluster statistics
        """
        total_clusters = self.db.query(Cluster).count()
        provisional_clusters = self.db.query(Cluster).filter(
            Cluster.provisional.is_(True)
        ).count()

        # Assets in clusters vs unclustered
        assets_in_clusters = self.db.query(Asset).filter(
            Asset.cluster_id.isnot(None)
        ).count()

        total_assets = self.db.query(Asset).count()

        # Average assets per cluster
        avg_assets = self.db.query(
            func.avg(func.count(Asset.id))
        ).select_from(Cluster).outerjoin(
            Asset, Asset.cluster_id == Cluster.id
        ).group_by(Cluster.id).scalar() or 0

        return {
            "total_clusters": total_clusters,
            "provisional_clusters": provisional_clusters,
            "confirmed_clusters": total_clusters - provisional_clusters,
            "total_assets": total_assets,
            "assets_in_clusters": assets_in_clusters,
            "unclustered_assets": total_assets - assets_in_clusters,
            "avg_assets_per_cluster": float(avg_assets)
        }

    def identify_merge_candidates(
        self,
        similarity_threshold: float = 0.85
    ) -> List[Tuple[Dict[str, Any], Dict[str, Any], float]]:
        """
        Identify cluster pairs that are similar and could be merged.

        Args:
            similarity_threshold: Minimum centroid similarity to suggest merge

        Returns:
            List of (cluster1, cluster2, similarity) tuples
        """
        clusters = self.db.query(Cluster).filter(
            Cluster.centroid.isnot(None)
        ).all()

        candidates = []

        # Compare all pairs
        for i, c1 in enumerate(clusters):
            for c2 in clusters[i+1:]:
                if c1.centroid and c2.centroid:
                    vec1 = np.array(c1.centroid, dtype=np.float32)
                    vec2 = np.array(c2.centroid, dtype=np.float32)

                    similarity = float(np.dot(vec1, vec2))

                    if similarity >= similarity_threshold:
                        candidates.append((
                            {"id": str(c1.id), "name": c1.name},
                            {"id": str(c2.id), "name": c2.name},
                            similarity
                        ))

        # Sort by similarity descending
        candidates.sort(key=lambda x: x[2], reverse=True)

        return candidates

    # ==================== Helper Methods ====================

    def _log_admin_action(
        self,
        action: str,
        target_type: str,
        target_id: UUID,
        performed_by: str,
        details: Dict[str, Any]
    ) -> None:
        """
        Log admin action to lineage table.

        Args:
            action: Action type
            target_type: Type of target (schema, cluster)
            target_id: ID of target
            performed_by: Admin identifier
            details: Action details
        """
        lineage = Lineage(
            request_id=f"admin_{performed_by}_{int(datetime.utcnow().timestamp())}",
            asset_id=None if target_type != "asset" else target_id,
            schema_id=target_id if target_type == "schema" else None,
            stage=f"admin_{action}",
            detail={
                "action": action,
                "target_type": target_type,
                "target_id": str(target_id),
                "performed_by": performed_by,
                **details
            },
            success=True
        )

        self.db.add(lineage)
        self.db.commit()
