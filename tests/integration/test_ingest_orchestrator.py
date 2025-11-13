"""
Integration tests for ingestion orchestrator.
"""

import pytest
import json
from io import BytesIO
from uuid import UUID
from fastapi import UploadFile

from src.catalog.database import get_db_session, init_db, engine
from src.catalog.models import Job, Asset, AssetRaw, Lineage, Base
from src.ingest.orchestrator import IngestionOrchestrator


@pytest.fixture(scope="function")
def setup_db():
    """Initialize database tables for testing."""
    from sqlalchemy import text
    # Enable pgvector extension
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    # Drop all tables
    Base.metadata.drop_all(bind=engine)
    # Create all tables
    Base.metadata.create_all(bind=engine)
    yield
    # Cleanup
    Base.metadata.drop_all(bind=engine)


class TestIngestionOrchestrator:
    """Integration tests for IngestionOrchestrator."""
    
    def test_ingest_json_single(self, setup_db):
        """Test ingestion of single JSON document."""
        with get_db_session() as db:
            orchestrator = IngestionOrchestrator(db)
            
            payload = json.dumps({"name": "John", "age": 30})
            result = orchestrator.ingest(payload=payload, owner="test_user")
            
            assert result["status"] == "accepted"
            assert "job_id" in result
            assert len(result["system_ids"]) == 1
            
            # Verify job was created
            job_id = UUID(result["job_id"])
            job = db.query(Job).filter(Job.id == job_id).first()
            assert job is not None
            assert job.job_type == "json"
            assert job.status == "queued"
            
            # Verify asset was created
            asset_id = UUID(result["system_ids"][0])
            asset = db.query(Asset).filter(Asset.id == asset_id).first()
            assert asset is not None
            assert asset.kind == "json"
            assert asset.owner == "test_user"
            assert asset.status == "queued"
    
    def test_ingest_json_batch(self, setup_db):
        """Test ingestion of JSON batch."""
        with get_db_session() as db:
            orchestrator = IngestionOrchestrator(db)
            
            payload = json.dumps([
                {"name": "John", "age": 30},
                {"name": "Jane", "age": 25}
            ])
            result = orchestrator.ingest(payload=payload)
            
            assert result["status"] == "accepted"
            assert len(result["system_ids"]) == 2
            
            # Verify both assets were created
            asset_ids = [UUID(sid) for sid in result["system_ids"]]
            assets = db.query(Asset).filter(
                Asset.id.in_(asset_ids)
            ).all()
            assert len(assets) == 2
    
    def test_ingest_file(self, setup_db):
        """Test ingestion of file."""
        with get_db_session() as db:
            orchestrator = IngestionOrchestrator(db)
            
            # Create a simple JPEG file
            from unittest.mock import Mock
            jpeg_data = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xd9'
            file = Mock(spec=UploadFile)
            file.filename = "test.jpg"
            file.file = BytesIO(jpeg_data)
            file.content_type = "image/jpeg"
            
            result = orchestrator.ingest(files=[file], owner="test_user")
            
            assert result["status"] == "accepted"
            assert len(result["system_ids"]) == 1
            
            # Verify asset and raw asset were created
            asset_id = UUID(result["system_ids"][0])
            asset = db.query(Asset).filter(Asset.id == asset_id).first()
            assert asset is not None
            assert asset.kind == "media"
            assert asset.raw_asset_id is not None
            
            raw_asset = db.query(AssetRaw).filter(
                AssetRaw.id == asset.raw_asset_id
            ).first()
            assert raw_asset is not None
            assert raw_asset.uri is not None
    
    def test_ingest_mixed(self, setup_db):
        """Test ingestion of mixed files and JSON."""
        with get_db_session() as db:
            orchestrator = IngestionOrchestrator(db)
            
            jpeg_data = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xd9'
            file = UploadFile(
                filename="test.jpg",
                file=BytesIO(jpeg_data)
            )
            file.content_type = "image/jpeg"
            
            payload = json.dumps({"description": "Test image"})
            
            result = orchestrator.ingest(files=[file], payload=payload)
            
            assert result["status"] == "accepted"
            assert len(result["system_ids"]) == 2  # One file + one JSON
    
    def test_idempotency_key(self, setup_db):
        """Test idempotency key handling."""
        with get_db_session() as db:
            orchestrator = IngestionOrchestrator(db)
            
            payload = json.dumps({"name": "John"})
            idempotency_key = "test-key-123"
            
            # First request
            result1 = orchestrator.ingest(
                payload=payload,
                idempotency_key=idempotency_key
            )
            
            # Second request with same key
            result2 = orchestrator.ingest(
                payload=payload,
                idempotency_key=idempotency_key
            )
            
            # Should return same job_id
            assert result1["job_id"] == result2["job_id"]
            assert "Duplicate request" in result2.get("message", "")
    
    def test_lineage_logging(self, setup_db):
        """Test that lineage is logged."""
        with get_db_session() as db:
            orchestrator = IngestionOrchestrator(db)
            
            payload = json.dumps({"name": "John"})
            result = orchestrator.ingest(payload=payload)
            
            # Verify lineage entries were created
            lineages = db.query(Lineage).filter(
                Lineage.request_id == result["request_id"]
            ).all()
            
            assert len(lineages) > 0
            assert any(l.stage == "ingest_accepted" for l in lineages)

