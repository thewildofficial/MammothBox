#!/usr/bin/env python3
"""
End-to-end test for Media Processing Pipeline.

Tests the complete flow:
1. Media file upload → AssetRaw/Asset creation → Queue → Worker processing
2. Media normalization, embedding, deduplication, clustering
3. Storage finalization and database updates
"""

import sys
import os
import time
import tempfile
from datetime import datetime
from uuid import uuid4
from io import BytesIO
from pathlib import Path

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from PIL import Image
import numpy as np

from src.queue.inproc import InProcessQueue
from src.queue.interface import QueueMessage
from src.catalog.database import get_db_session, check_database_connection, engine
from src.catalog.models import Job, Asset, AssetRaw, Cluster, VideoFrame, Lineage
from sqlalchemy import text
from src.queue.supervisor import WorkerSupervisor
from src.queue.processors import MediaJobProcessor, JsonJobProcessor
from src.storage.factory import get_storage_adapter, reset_storage_adapter


def create_test_image(width=800, height=600, color='red'):
    """Create a test image."""
    img = Image.new('RGB', (width, height), color=color)
    buffer = BytesIO()
    img.save(buffer, format='JPEG', quality=95)
    buffer.seek(0)
    return buffer.read()


def init_test_db():
    """Initialize database with all required tables."""
    try:
        with engine.connect() as conn:
            # Create ENUM types if they don't exist
            conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE job_type AS ENUM ('media', 'json');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE job_status AS ENUM ('queued', 'processing', 'done', 'failed');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE asset_kind AS ENUM ('media', 'json');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE asset_status AS ENUM ('queued', 'processing', 'done', 'failed');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            conn.commit()
            
            # Create extension for pgvector if not exists (optional for testing)
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                conn.commit()
            except Exception as e:
                print(f"⚠️  Warning: pgvector extension not available: {e}")
                print("   Continuing without vector extension (some features may be limited)")
                conn.rollback()
            
            # Import and create all tables
            from src.catalog.models import Base
            Base.metadata.create_all(bind=engine)
            conn.commit()
            
        return True
    except Exception as e:
        print(f"⚠️  Failed to initialize test database: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_media_processing_e2e():
    """Test complete media processing pipeline."""
    print("\n" + "="*80)
    print("E2E TEST: Media Processing Pipeline")
    print("="*80)
    
    # Check database availability
    if not check_database_connection():
        print("⚠️  Skipping test: Database not available")
        return None
    
    # Initialize database
    if not init_test_db():
        print("❌ Failed to initialize test database")
        return False
    
    print("✅ Database initialized")
    
    # Reset storage adapter for clean test
    reset_storage_adapter()
    storage = get_storage_adapter()
    
    queue = None
    supervisor = None
    job_ids = []
    asset_ids = []
    
    try:
        # Setup queue and supervisor
        queue = InProcessQueue()
        processors = {
            "media": MediaJobProcessor(),
            "json": JsonJobProcessor()
        }
        supervisor = WorkerSupervisor(queue, processors, num_workers=2)
        supervisor.start()
        print("✅ Worker supervisor started")
        
        time.sleep(2)  # Let workers start and preload models
        
        # Create test images
        print("\n📸 Creating test images...")
        image1_data = create_test_image(1920, 1080, 'red')
        image2_data = create_test_image(800, 600, 'blue')
        image3_data = create_test_image(1200, 800, 'green')
        
        # Create job for media processing
        job_id = uuid4()
        request_id = str(uuid4())
        
        print(f"\n📤 Uploading {3} media files...")
        
        # Store raw files and create AssetRaw/Asset records
        with get_db_session() as db:
            asset_raw_ids = []
            asset_ids_list = []
            
            for idx, (img_data, color) in enumerate([
                (image1_data, 'red'),
                (image2_data, 'blue'),
                (image3_data, 'green')
            ]):
                # Store raw file
                part_id = f"part_{idx}"
                filename = f"test_{color}_{idx}.jpg"
                raw_uri = storage.store_raw(request_id, part_id, BytesIO(img_data), filename)
                
                # Create AssetRaw
                asset_raw = AssetRaw(
                    request_id=request_id,
                    part_id=part_id,
                    uri=raw_uri,
                    size_bytes=len(img_data),
                    content_type='image/jpeg'
                )
                db.add(asset_raw)
                db.flush()
                asset_raw_ids.append(asset_raw.id)
                
                # Create Asset
                asset = Asset(
                    kind="media",
                    uri=raw_uri,
                    size_bytes=len(img_data),
                    content_type='image/jpeg',
                    owner="e2e_test",
                    status="queued",
                    raw_asset_id=asset_raw.id
                )
                db.add(asset)
                db.flush()
                asset_ids_list.append(asset.id)
                asset_ids.append(str(asset.id))
            
            # Create job
            job = Job(
                id=job_id,
                request_id=request_id,
                job_type="media",
                status="queued",
                job_data={
                    "job_id": str(job_id),
                    "request_id": request_id,
                    "asset_ids": asset_ids,
                    "asset_raw_ids": [str(aid) for aid in asset_raw_ids],
                    "owner": "e2e_test"
                },
                asset_ids=asset_ids_list
            )
            db.add(job)
            db.commit()
            job_ids.append(job_id)
        
        # Enqueue job
        queue_message = QueueMessage(
            job_id=job_id,
            job_type="media",
            job_data={
                "job_id": str(job_id),
                "request_id": request_id,
                "asset_ids": asset_ids,
                "asset_raw_ids": [str(aid) for aid in asset_raw_ids],
                "owner": "e2e_test"
            },
            created_at=datetime.utcnow()
        )
        queue.enqueue(queue_message)
        print(f"✅ Enqueued job {job_id}")
        
        # Wait for processing
        print("\n⏳ Waiting for media processing...")
        max_wait = 120.0  # 2 minutes for media processing (includes model loading)
        start_wait = time.time()
        
        while time.time() - start_wait < max_wait:
            completed = 0
            failed = 0
            processing = 0
            
            with get_db_session() as db:
                job = db.query(Job).filter(Job.id == job_id).first()
                if job:
                    if job.status == "done":
                        completed = len(asset_ids)
                        break
                    elif job.status == "failed":
                        failed = len(asset_ids)
                        break
                    elif job.status == "processing":
                        processing = len(asset_ids)
                
                # Check individual assets
                for asset_id_str in asset_ids:
                    from uuid import UUID
                    asset_id = UUID(asset_id_str) if isinstance(asset_id_str, str) else asset_id_str
                    try:
                        asset = db.query(Asset).filter(Asset.id == asset_id).first()
                        if asset:
                            if asset.status == "done":
                                completed += 1
                            elif asset.status == "failed":
                                failed += 1
                            elif asset.status == "processing":
                                processing += 1
                    except Exception:
                        pass
            
            elapsed = time.time() - start_wait
            if completed + failed == len(asset_ids):
                break
            
            if int(elapsed) % 5 == 0 and elapsed > 0:
                print(f"  Progress: {completed} done, {failed} failed, {processing} processing (elapsed: {elapsed:.1f}s)")
            
            time.sleep(1)
        
        # Analyze results
        print("\n" + "="*80)
        print("RESULTS ANALYSIS")
        print("="*80)
        
        with get_db_session() as db:
            # Job status
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                print(f"\n📋 Job Status: {job.status}")
                if job.error_message:
                    print(f"   Error: {job.error_message}")
            
            # Asset analysis
            print(f"\n📊 Asset Analysis:")
            success_count = 0
            cluster_ids = set()
            
            for asset_id_str in asset_ids:
                try:
                    from uuid import UUID
                    asset_id = UUID(asset_id_str) if isinstance(asset_id_str, str) else asset_id_str
                    asset = db.query(Asset).filter(Asset.id == asset_id).first()
                    if asset:
                        print(f"\n  Asset {asset.id}:")
                        print(f"    Status: {asset.status}")
                        print(f"    Content Type: {asset.content_type}")
                        print(f"    Size: {asset.size_bytes} bytes")
                        print(f"    SHA256: {asset.sha256[:16] if asset.sha256 else 'N/A'}...")
                        
                        if asset.status == "done":
                            success_count += 1
                            print(f"    ✅ Processing successful")
                            
                            if asset.cluster_id:
                                cluster_ids.add(asset.cluster_id)
                                cluster = db.query(Cluster).filter(Cluster.id == asset.cluster_id).first()
                                if cluster:
                                    print(f"    Cluster: {cluster.name} (ID: {cluster.id})")
                                    print(f"    Cluster Threshold: {cluster.threshold}")
                                    print(f"    Provisional: {cluster.provisional}")
                            
                            if asset.embedding:
                                emb_array = np.array(asset.embedding)
                                print(f"    Embedding: shape={emb_array.shape}, norm={np.linalg.norm(emb_array):.3f}")
                            
                            if asset.tags:
                                print(f"    Tags: {asset.tags}")
                            
                            if asset.metadata:
                                metadata = asset.metadata
                                print(f"    Metadata:")
                                if 'width' in metadata:
                                    print(f"      Dimensions: {metadata.get('width')}x{metadata.get('height')}")
                                if 'perceptual_hash' in metadata:
                                    print(f"      Perceptual Hash: {metadata['perceptual_hash'][:16]}...")
                        else:
                            print(f"    ❌ Processing failed")
                            if asset.status == "failed":
                                # Check lineage for error
                                lineage = db.query(Lineage).filter(
                                    Lineage.asset_id == asset.id,
                                    Lineage.success == False
                                ).first()
                                if lineage and lineage.error_message:
                                    print(f"    Error: {lineage.error_message}")
                except Exception as e:
                    print(f"    ⚠️  Error analyzing asset {asset_id_str}: {e}")
            
            # Cluster analysis
            print(f"\n🎯 Cluster Analysis:")
            print(f"  Total clusters created: {len(cluster_ids)}")
            for cluster_id in cluster_ids:
                cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
                if cluster:
                    asset_count = db.query(Asset).filter(Asset.cluster_id == cluster_id).count()
                    print(f"\n  Cluster: {cluster.name}")
                    print(f"    ID: {cluster.id}")
                    print(f"    Assets: {asset_count}")
                    print(f"    Threshold: {cluster.threshold}")
                    print(f"    Provisional: {cluster.provisional}")
                    if cluster.centroid:
                        centroid_norm = np.linalg.norm(np.array(cluster.centroid))
                        print(f"    Centroid norm: {centroid_norm:.3f}")
            
            # Performance metrics
            print(f"\n⚡ Performance Metrics:")
            lineage_entries = db.query(Lineage).filter(Lineage.request_id == request_id).all()
            stages = {}
            for entry in lineage_entries:
                stage = entry.stage
                if stage not in stages:
                    stages[stage] = {'count': 0, 'success': 0, 'failed': 0}
                stages[stage]['count'] += 1
                if entry.success:
                    stages[stage]['success'] += 1
                else:
                    stages[stage]['failed'] += 1
            
            for stage, stats in stages.items():
                print(f"  {stage}: {stats['success']}/{stats['count']} successful")
            
            # Summary
            print(f"\n📈 Summary:")
            print(f"  Total assets: {len(asset_ids)}")
            print(f"  Successful: {success_count}")
            print(f"  Failed: {len(asset_ids) - success_count}")
            print(f"  Success rate: {(success_count / len(asset_ids) * 100):.1f}%")
            print(f"  Clusters created: {len(cluster_ids)}")
        
        success_rate = (success_count / len(asset_ids)) * 100 if asset_ids else 0
        return success_rate >= 80
        
    except Exception as e:
        print(f"❌ E2E test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        if supervisor:
            supervisor.stop()
        if queue:
            queue.close()
        
        # Clean up test data
        if job_ids:
            try:
                with get_db_session() as db:
                    # Delete in reverse order of dependencies
                    db.query(Lineage).filter(Lineage.request_id == request_id).delete()
                    from uuid import UUID
                    asset_uuid_list = [UUID(aid) if isinstance(aid, str) else aid for aid in asset_ids]
                    db.query(VideoFrame).filter(VideoFrame.asset_id.in_(asset_uuid_list)).delete(synchronize_session=False)
                    db.query(Asset).filter(Asset.id.in_(asset_uuid_list)).delete(synchronize_session=False)
                    db.query(AssetRaw).filter(AssetRaw.request_id == request_id).delete()
                    db.query(Job).filter(Job.id.in_(job_ids)).delete(synchronize_session=False)
                    db.commit()
            except Exception as e:
                print(f"⚠️  Warning: Failed to clean up test data: {e}")


def main():
    """Run E2E tests."""
    print("="*80)
    print("MEDIA PROCESSING PIPELINE - END-TO-END TEST")
    print("="*80)
    print(f"Started at: {datetime.now().isoformat()}\n")
    
    result = test_media_processing_e2e()
    
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    if result is None:
        print("⏭️  TEST SKIPPED (database not available)")
        return 0
    elif result:
        print("✅ TEST PASSED")
        return 0
    else:
        print("❌ TEST FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())

