"""
Unit tests for admin handlers (Phase 8).

Tests schema management, cluster operations, and statistics.
"""

import pytest
from uuid import uuid4

import numpy as np

from src.admin.handlers import AdminHandlers, AdminError
from src.catalog.models import Asset, Cluster, SchemaDef


class TestSchemaManagement:
    """Test schema approval and rejection operations."""

    def test_list_schemas_empty(self, db_session):
        """Test listing schemas with no data."""
        admin = AdminHandlers(db_session)
        schemas = admin.list_schemas()

        assert schemas == []

    def test_list_schemas_with_data(self, db_session):
        """Test listing schemas with filtering."""
        # Create test schemas
        schema1 = SchemaDef(
            id=uuid4(),
            name="test_schema_1",
            structure_hash="hash1",
            storage_choice="sql",
            status="provisional",
            sample_size=10,
            ddl="CREATE TABLE test_schema_1 (id INT);"
        )
        schema2 = SchemaDef(
            id=uuid4(),
            name="test_schema_2",
            structure_hash="hash2",
            storage_choice="jsonb",
            status="active",
            sample_size=15,
            ddl=None
        )
        db_session.add_all([schema1, schema2])
        db_session.commit()

        admin = AdminHandlers(db_session)

        # Test list all
        all_schemas = admin.list_schemas()
        assert len(all_schemas) == 2

        # Test filter by status
        provisional = admin.list_schemas(status="provisional")
        assert len(provisional) == 1
        assert provisional[0]["name"] == "test_schema_1"

        # Test filter by storage choice
        sql_schemas = admin.list_schemas(storage_choice="sql")
        assert len(sql_schemas) == 1
        assert sql_schemas[0]["storage_choice"] == "sql"

    def test_get_schema(self, db_session):
        """Test getting schema details."""
        schema = SchemaDef(
            id=uuid4(),
            name="test_schema",
            structure_hash="hash123",
            storage_choice="sql",
            status="provisional",
            sample_size=20,
            ddl="CREATE TABLE test (id INT);"
        )
        db_session.add(schema)
        db_session.commit()

        admin = AdminHandlers(db_session)
        result = admin.get_schema(schema.id)

        assert result["id"] == str(schema.id)
        assert result["name"] == "test_schema"
        assert result["storage_choice"] == "sql"
        assert result["asset_count"] == 0

    def test_get_schema_not_found(self, db_session):
        """Test getting non-existent schema."""
        admin = AdminHandlers(db_session)

        with pytest.raises(AdminError, match="not found"):
            admin.get_schema(uuid4())

    def test_get_pending_schemas(self, db_session):
        """Test getting provisional schemas."""
        schema1 = SchemaDef(
            id=uuid4(),
            name="pending_1",
            structure_hash="hash1",
            storage_choice="sql",
            status="provisional",
            sample_size=10
        )
        schema2 = SchemaDef(
            id=uuid4(),
            name="active_1",
            structure_hash="hash2",
            storage_choice="sql",
            status="active",
            sample_size=10
        )
        db_session.add_all([schema1, schema2])
        db_session.commit()

        admin = AdminHandlers(db_session)
        pending = admin.get_pending_schemas()

        assert len(pending) == 1
        assert pending[0]["name"] == "pending_1"


class TestClusterManagement:
    """Test cluster operations."""

    def test_list_clusters_empty(self, db_session):
        """Test listing clusters with no data."""
        admin = AdminHandlers(db_session)
        clusters = admin.list_clusters()

        assert clusters == []

    def test_list_clusters_with_data(self, db_session):
        """Test listing clusters with filtering."""
        cluster1 = Cluster(
            id=uuid4(),
            name="Cluster 1",
            threshold=0.85,
            provisional=True,
            centroid=[0.1] * 512
        )
        cluster2 = Cluster(
            id=uuid4(),
            name="Cluster 2",
            threshold=0.90,
            provisional=False,
            centroid=[0.2] * 512
        )
        db_session.add_all([cluster1, cluster2])
        db_session.commit()

        # Add assets to cluster1
        asset1 = Asset(
            id=uuid4(),
            kind="image",
            cluster_id=cluster1.id,
            embedding=[0.1] * 512
        )
        asset2 = Asset(
            id=uuid4(),
            kind="image",
            cluster_id=cluster1.id,
            embedding=[0.15] * 512
        )
        db_session.add_all([asset1, asset2])
        db_session.commit()

        admin = AdminHandlers(db_session)

        # Test list all
        all_clusters = admin.list_clusters()
        assert len(all_clusters) == 2

        # Test provisional filter
        provisional = admin.list_clusters(provisional_only=True)
        assert len(provisional) == 1
        assert provisional[0]["name"] == "Cluster 1"

        # Test min_assets filter
        with_assets = admin.list_clusters(min_assets=1)
        assert len(with_assets) == 1
        assert with_assets[0]["asset_count"] == 2

    def test_get_cluster(self, db_session):
        """Test getting cluster details with statistics."""
        cluster = Cluster(
            id=uuid4(),
            name="Test Cluster",
            threshold=0.85,
            provisional=True,
            centroid=np.random.rand(512).tolist()
        )
        db_session.add(cluster)
        db_session.commit()

        # Add assets
        for _ in range(3):
            asset = Asset(
                id=uuid4(),
                kind="image",
                cluster_id=cluster.id,
                embedding=np.random.rand(512).tolist()
            )
            db_session.add(asset)
        db_session.commit()

        admin = AdminHandlers(db_session)
        result = admin.get_cluster(cluster.id)

        assert result["id"] == str(cluster.id)
        assert result["name"] == "Test Cluster"
        assert result["asset_count"] == 3
        assert result["centroid_quality"] is not None
        assert "mean" in result["centroid_quality"]

    def test_get_cluster_not_found(self, db_session):
        """Test getting non-existent cluster."""
        admin = AdminHandlers(db_session)

        with pytest.raises(AdminError, match="not found"):
            admin.get_cluster(uuid4())

    def test_rename_cluster(self, db_session):
        """Test renaming a cluster."""
        cluster = Cluster(
            id=uuid4(),
            name="Old Name",
            threshold=0.85,
            provisional=True
        )
        db_session.add(cluster)
        db_session.commit()

        admin = AdminHandlers(db_session)
        result = admin.rename_cluster(
            cluster_id=cluster.id,
            new_name="New Name",
            performed_by="test_admin"
        )

        assert result["name"] == "New Name"

        # Verify in database
        db_session.refresh(cluster)
        assert cluster.name == "New Name"

    def test_rename_cluster_collision(self, db_session):
        """Test renaming cluster to existing name."""
        cluster1 = Cluster(id=uuid4(), name="Cluster 1",
                           threshold=0.85, provisional=True)
        cluster2 = Cluster(id=uuid4(), name="Cluster 2",
                           threshold=0.85, provisional=True)
        db_session.add_all([cluster1, cluster2])
        db_session.commit()

        admin = AdminHandlers(db_session)

        with pytest.raises(AdminError, match="already exists"):
            admin.rename_cluster(
                cluster_id=cluster1.id,
                new_name="Cluster 2",
                performed_by="test_admin"
            )

    def test_merge_clusters(self, db_session):
        """Test merging multiple clusters."""
        # Create target cluster
        target = Cluster(
            id=uuid4(),
            name="Target",
            threshold=0.85,
            provisional=False,
            centroid=np.random.rand(512).tolist()
        )
        db_session.add(target)

        # Create source clusters with assets
        source1 = Cluster(
            id=uuid4(),
            name="Source 1",
            threshold=0.85,
            provisional=True,
            centroid=np.random.rand(512).tolist()
        )
        source2 = Cluster(
            id=uuid4(),
            name="Source 2",
            threshold=0.85,
            provisional=True,
            centroid=np.random.rand(512).tolist()
        )
        db_session.add_all([source1, source2])
        db_session.commit()

        # Add assets to source clusters
        assets = []
        for i, cluster in enumerate([source1, source2]):
            for _ in range(2):
                asset = Asset(
                    id=uuid4(),
                    kind="image",
                    cluster_id=cluster.id,
                    embedding=np.random.rand(512).tolist()
                )
                assets.append(asset)
        db_session.add_all(assets)
        db_session.commit()

        admin = AdminHandlers(db_session)
        result = admin.merge_clusters(
            source_cluster_ids=[source1.id, source2.id],
            target_cluster_id=target.id,
            performed_by="test_admin"
        )

        assert result["name"] == "Target"
        assert result["asset_count"] == 4

        # Verify source clusters deleted
        assert db_session.query(Cluster).filter(
            Cluster.id == source1.id).first() is None
        assert db_session.query(Cluster).filter(
            Cluster.id == source2.id).first() is None

        # Verify assets moved
        target_assets = db_session.query(Asset).filter(
            Asset.cluster_id == target.id).all()
        assert len(target_assets) == 4

    def test_merge_clusters_into_self(self, db_session):
        """Test merging cluster into itself raises error."""
        cluster = Cluster(id=uuid4(), name="Test",
                          threshold=0.85, provisional=True)
        db_session.add(cluster)
        db_session.commit()

        admin = AdminHandlers(db_session)

        with pytest.raises(AdminError, match="into itself"):
            admin.merge_clusters(
                source_cluster_ids=[cluster.id],
                target_cluster_id=cluster.id,
                performed_by="test_admin"
            )

    def test_update_cluster_threshold(self, db_session):
        """Test updating cluster threshold."""
        cluster = Cluster(
            id=uuid4(),
            name="Test",
            threshold=0.85,
            provisional=True
        )
        db_session.add(cluster)
        db_session.commit()

        admin = AdminHandlers(db_session)
        result = admin.update_cluster_threshold(
            cluster_id=cluster.id,
            threshold=0.90,
            performed_by="test_admin"
        )

        assert result["threshold"] == 0.90

        # Verify in database
        db_session.refresh(cluster)
        assert cluster.threshold == 0.90

    def test_update_threshold_invalid_range(self, db_session):
        """Test updating threshold with invalid value."""
        cluster = Cluster(id=uuid4(), name="Test",
                          threshold=0.85, provisional=True)
        db_session.add(cluster)
        db_session.commit()

        admin = AdminHandlers(db_session)

        with pytest.raises(AdminError, match="between 0.0 and 1.0"):
            admin.update_cluster_threshold(
                cluster_id=cluster.id,
                threshold=1.5,
                performed_by="test_admin"
            )

    def test_confirm_cluster(self, db_session):
        """Test confirming a provisional cluster."""
        cluster = Cluster(
            id=uuid4(),
            name="Provisional",
            threshold=0.85,
            provisional=True
        )
        db_session.add(cluster)
        db_session.commit()

        admin = AdminHandlers(db_session)
        result = admin.confirm_cluster(
            cluster_id=cluster.id,
            performed_by="test_admin"
        )

        assert result["provisional"] is False

        # Verify in database
        db_session.refresh(cluster)
        assert cluster.provisional is False

    def test_confirm_already_confirmed(self, db_session):
        """Test confirming already confirmed cluster."""
        cluster = Cluster(
            id=uuid4(),
            name="Already Confirmed",
            threshold=0.85,
            provisional=False
        )
        db_session.add(cluster)
        db_session.commit()

        admin = AdminHandlers(db_session)

        with pytest.raises(AdminError, match="already confirmed"):
            admin.confirm_cluster(
                cluster_id=cluster.id,
                performed_by="test_admin"
            )


class TestStatistics:
    """Test statistics and analytics."""

    def test_cluster_statistics(self, db_session):
        """Test cluster statistics calculation."""
        # Create clusters
        cluster1 = Cluster(id=uuid4(), name="C1",
                           threshold=0.85, provisional=True)
        cluster2 = Cluster(id=uuid4(), name="C2",
                           threshold=0.85, provisional=False)
        db_session.add_all([cluster1, cluster2])
        db_session.commit()

        # Add assets
        asset1 = Asset(id=uuid4(), kind="image", cluster_id=cluster1.id)
        asset2 = Asset(id=uuid4(), kind="image", cluster_id=cluster1.id)
        asset3 = Asset(id=uuid4(), kind="image")  # Unclustered
        db_session.add_all([asset1, asset2, asset3])
        db_session.commit()

        admin = AdminHandlers(db_session)
        stats = admin.get_cluster_statistics()

        assert stats["total_clusters"] == 2
        assert stats["provisional_clusters"] == 1
        assert stats["confirmed_clusters"] == 1
        assert stats["total_assets"] == 3
        assert stats["assets_in_clusters"] == 2
        assert stats["unclustered_assets"] == 1

    def test_identify_merge_candidates(self, db_session):
        """Test identifying similar clusters for merging."""
        # Create clusters with similar centroids
        vec1 = np.random.rand(512)
        vec1 = vec1 / np.linalg.norm(vec1)

        # Create similar vector
        vec2 = vec1 + np.random.rand(512) * 0.05
        vec2 = vec2 / np.linalg.norm(vec2)

        cluster1 = Cluster(
            id=uuid4(),
            name="Similar 1",
            threshold=0.85,
            provisional=True,
            centroid=vec1.tolist()
        )
        cluster2 = Cluster(
            id=uuid4(),
            name="Similar 2",
            threshold=0.85,
            provisional=True,
            centroid=vec2.tolist()
        )
        db_session.add_all([cluster1, cluster2])
        db_session.commit()

        admin = AdminHandlers(db_session)
        candidates = admin.identify_merge_candidates(similarity_threshold=0.80)

        # Should find the similar pair
        assert len(candidates) >= 1

        # Check structure
        c1, c2, sim = candidates[0]
        assert "id" in c1 and "name" in c1
        assert "id" in c2 and "name" in c2
        assert 0.80 <= sim <= 1.0


class TestAdminLogging:
    """Test admin action logging."""

    def test_schema_approval_logged(self, db_session):
        """Test that schema approval is logged to lineage."""
        from src.catalog.models import Lineage

        schema = SchemaDef(
            id=uuid4(),
            name="test_schema",
            structure_hash="hash123",
            storage_choice="jsonb",
            status="provisional",
            sample_size=10
        )
        db_session.add(schema)
        db_session.commit()

        admin = AdminHandlers(db_session)

        # Approve schema (will create lineage entry)
        admin.approve_schema(
            schema_id=schema.id,
            reviewed_by="test_admin"
        )

        # Check lineage
        lineage_entries = db_session.query(Lineage).filter(
            Lineage.stage.like("%admin%")
        ).all()

        assert len(lineage_entries) > 0
        assert lineage_entries[0].success is True

    def test_cluster_rename_logged(self, db_session):
        """Test that cluster rename is logged to lineage."""
        from src.catalog.models import Lineage

        cluster = Cluster(id=uuid4(), name="Old",
                          threshold=0.85, provisional=True)
        db_session.add(cluster)
        db_session.commit()

        admin = AdminHandlers(db_session)
        admin.rename_cluster(
            cluster_id=cluster.id,
            new_name="New",
            performed_by="test_admin"
        )

        # Check lineage
        lineage_entries = db_session.query(Lineage).filter(
            Lineage.stage == "admin_cluster_renamed"
        ).all()

        assert len(lineage_entries) == 1
        assert lineage_entries[0].detail["old_name"] == "Old"
        assert lineage_entries[0].detail["new_name"] == "New"


# Fixtures

@pytest.fixture
def db_session():
    """Create in-memory SQLite session for testing."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.catalog.models import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()
