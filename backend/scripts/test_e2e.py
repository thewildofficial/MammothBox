#!/usr/bin/env python3
"""
End-to-end test for Job Queue & Worker System.

Tests the complete flow:
1. API ingestion → Queue → Worker processing → Status tracking
2. Tests both in-process and Redis queue backends
3. Tests retry logic and dead-letter queue
"""

import sys
import os
import time
import json
from datetime import datetime
from uuid import uuid4

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.queue.inproc import InProcessQueue
from src.queue.redis import RedisQueue
from src.queue.interface import QueueMessage
from src.catalog.database import get_db_session, check_database_connection, engine
from src.catalog.models import Job, Asset
from sqlalchemy import text
from src.queue.supervisor import WorkerSupervisor
from src.queue.processors import JsonJobProcessor


def clear_redis_queue(redis_url: str = "redis://localhost:6379/0"):
    """Clear all Redis queue data for test isolation."""
    try:
        import redis
        from urllib.parse import urlparse
        
        parsed = urlparse(redis_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        db = int(parsed.path.lstrip('/')) if parsed.path else 0
        
        client = redis.Redis(host=host, port=port, db=db, decode_responses=False)
        
        # Clear queue keys
        queue_keys = [
            "queue:jobs",
            "queue:processing",
            "queue:dlq",
        ]
        
        for key in queue_keys:
            client.delete(key)
        
        # Clear job metadata keys
        meta_keys = client.keys("queue:meta:*")
        if meta_keys:
            client.delete(*meta_keys)
        
        # Clear DLQ keys
        dlq_keys = client.keys("queue:dlq:*")
        if dlq_keys:
            client.delete(*dlq_keys)
        
        client.close()
        return True
    except Exception as e:
        print(f"⚠️  Warning: Failed to clear Redis queue: {e}")
        return False


def check_database_available():
    """Check if database is available and accessible."""
    try:
        return check_database_connection()
    except Exception as e:
        print(f"⚠️  Database check failed: {e}")
        return False


def init_test_db():
    """Initialize database with only job table (skip vector-dependent tables)."""
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
            conn.commit()
            
            # Create job table if it doesn't exist
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS job (
                    id UUID PRIMARY KEY,
                    request_id VARCHAR(255) NOT NULL,
                    job_type job_type NOT NULL,
                    status job_status NOT NULL DEFAULT 'queued',
                    job_data JSONB NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 3,
                    next_retry_at TIMESTAMP,
                    dead_letter BOOLEAN NOT NULL DEFAULT false,
                    error_message TEXT,
                    asset_ids UUID[],
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP
                );
            """))
            
            # Create indexes
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_job_request_id ON job(request_id);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_job_status ON job(status);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_job_type ON job(job_type);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_job_next_retry_at ON job(next_retry_at);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_job_dead_letter ON job(dead_letter);"))
            
            conn.commit()
        return True
    except Exception as e:
        print(f"⚠️  Failed to initialize test database: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_redis_connection():
    """Test 1: Redis connection."""
    print("\n" + "="*80)
    print("TEST 1: Redis Connection")
    print("="*80)
    
    try:
        # Clear queue before test for isolation
        clear_redis_queue()
        
        queue = RedisQueue(redis_url="redis://localhost:6379/0")
        size = queue.size()
        print(f"✅ Redis connected successfully. Queue size: {size}")
        queue.close()
        return True
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_redis_queue_operations():
    """Test 2: Redis queue basic operations."""
    print("\n" + "="*80)
    print("TEST 2: Redis Queue Operations")
    print("="*80)
    
    queue = None
    try:
        # Clear queue before test for isolation
        clear_redis_queue()
        
        queue = RedisQueue(redis_url="redis://localhost:6379/0")
        
        # Verify queue is empty
        initial_size = queue.size()
        if initial_size > 0:
            print(f"⚠️  Warning: Queue not empty at start (size: {initial_size}), clearing...")
            clear_redis_queue()
            initial_size = queue.size()
        
        assert initial_size == 0, f"Expected empty queue, got size {initial_size}"
        
        # Enqueue
        job_id = uuid4()
        message = QueueMessage(
            job_id=job_id,
            job_type="json",
            job_data={"test": "data"},
            priority=0,
            created_at=datetime.utcnow()
        )
        queue.enqueue(message)
        print(f"✅ Enqueued job {job_id}")
        
        # Check size
        size = queue.size()
        assert size == 1, f"Expected queue size 1, got {size}"
        print(f"✅ Queue size: {size}")
        
        # Dequeue
        dequeued = queue.dequeue(timeout=1.0)
        assert dequeued is not None, "Failed to dequeue"
        assert dequeued.job_id == job_id, "Dequeued wrong job"
        print(f"✅ Dequeued job {dequeued.job_id}")
        
        # Ack
        queue.ack(job_id)
        print(f"✅ Acknowledged job {job_id}")
        
        # Final size
        final_size = queue.size()
        assert final_size == 0, f"Expected queue size 0, got {final_size}"
        print(f"✅ Final queue size: {final_size}")
        
        return True
    except Exception as e:
        print(f"❌ Redis queue operations failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if queue:
            queue.close()
        # Cleanup after test
        clear_redis_queue()


def test_redis_retry_logic():
    """Test 3: Redis retry logic."""
    print("\n" + "="*80)
    print("TEST 3: Redis Retry Logic")
    print("="*80)
    
    queue = None
    try:
        # Clear queue before test for isolation
        clear_redis_queue()
        
        queue = RedisQueue(redis_url="redis://localhost:6379/0")
        
        # Verify queue and DLQ are empty
        initial_size = queue.size()
        initial_dlq_size = queue.get_dlq_size()
        if initial_size > 0 or initial_dlq_size > 0:
            print(f"⚠️  Warning: Queue/DLQ not empty at start (size: {initial_size}, DLQ: {initial_dlq_size}), clearing...")
            clear_redis_queue()
            initial_size = queue.size()
            initial_dlq_size = queue.get_dlq_size()
        
        job_id = uuid4()
        message = QueueMessage(
            job_id=job_id,
            job_type="json",
            job_data={},
            retry_count=0,
            max_retries=3
        )
        
        queue.enqueue(message)
        dequeued = queue.dequeue(timeout=1.0)
        assert dequeued is not None, "Failed to dequeue initial message"
        
        # Nack should schedule retry
        queue.nack(job_id, "Test error")
        print(f"✅ Nacked job {job_id}")
        
        # Check queue size (should be 1 for retry)
        size = queue.size()
        assert size == 1, f"Expected queue size 1 after retry, got {size} (initial was {initial_size})"
        print(f"✅ Job re-enqueued for retry. Queue size: {size}")
        
        # Test DLQ
        job_id2 = uuid4()
        message2 = QueueMessage(
            job_id=job_id2,
            job_type="json",
            job_data={},
            retry_count=3,  # Already at max
            max_retries=3
        )
        queue.enqueue(message2)
        dequeued2 = queue.dequeue(timeout=1.0)
        assert dequeued2 is not None, "Failed to dequeue message2"
        queue.nack(job_id2, "Final error")
        
        dlq_size = queue.get_dlq_size()
        assert dlq_size >= 1, f"Expected DLQ size >= 1, got {dlq_size} (initial was {initial_dlq_size})"
        print(f"✅ Job moved to DLQ. DLQ size: {dlq_size}")
        
        return True
    except Exception as e:
        print(f"❌ Redis retry logic failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if queue:
            queue.close()
        # Cleanup after test
        clear_redis_queue()


def test_end_to_end_processing():
    """Test 4: End-to-end job processing with database."""
    print("\n" + "="*80)
    print("TEST 4: End-to-End Processing (Database + Queue + Workers)")
    print("="*80)
    
    # Check database availability first
    if not check_database_available():
        print("⚠️  Skipping test: Database not available")
        print("   To run this test, ensure PostgreSQL is running and configured")
        print("   Check your database connection settings in .env or environment variables")
        return None  # Skip, don't fail
    
    queue = None
    supervisor = None
    job_ids = []
    
    try:
        # Initialize database (only job table, skip vector-dependent tables)
        if not init_test_db():
            print("❌ Failed to initialize test database")
            return False
        print("✅ Database initialized")
        
        # Use in-process queue for this test (simpler)
        queue = InProcessQueue()
        processors = {"json": JsonJobProcessor()}
        supervisor = WorkerSupervisor(queue, processors, num_workers=2)
        supervisor.start()
        print("✅ Worker supervisor started")
        
        time.sleep(1)  # Let workers start
        
        # Create test jobs
        for i in range(5):
            job_id = uuid4()
            request_id = str(uuid4())
            
            # Prepare job_data before creating job (to avoid session issues)
            job_data = {
                "job_id": str(job_id),
                "documents": [{"id": i, "name": f"TestUser{i}", "value": i * 10}],
                "request_id": request_id,
                "owner": "e2e_test"
            }
            
            with get_db_session() as db:
                job = Job(
                    id=job_id,
                    request_id=request_id,
                    job_type="json",
                    status="queued",
                    job_data=job_data
                )
                db.add(job)
                db.commit()
            
            message = QueueMessage(
                job_id=job_id,
                job_type="json",
                job_data=job_data,  # Use the prepared dict, not job.job_data
                created_at=datetime.utcnow()
            )
            queue.enqueue(message)
            job_ids.append(job_id)
            print(f"✅ Created and enqueued job {job_id}")
        
        # Wait for processing
        print("\n⏳ Waiting for jobs to process...")
        max_wait = 60.0  # Increased wait time
        start_wait = time.time()
        
        while time.time() - start_wait < max_wait:
            completed = 0
            failed = 0
            processing = 0
            queued = 0
            
            with get_db_session() as db:
                for job_id in job_ids:
                    job = db.query(Job).filter(Job.id == job_id).first()
                    if job:
                        if job.status == "done":
                            completed += 1
                        elif job.status == "failed":
                            failed += 1
                            if job.error_message:
                                print(f"⚠️  Job {job_id} failed: {job.error_message}")
                        elif job.status == "processing":
                            processing += 1
                        elif job.status == "queued":
                            queued += 1
            
            elapsed = time.time() - start_wait
            if completed + failed == len(job_ids):
                break
            
            # Print progress every 5 seconds
            if int(elapsed) % 5 == 0 and elapsed > 0:
                print(f"  Progress: {completed} done, {failed} failed, {processing} processing, {queued} queued (elapsed: {elapsed:.1f}s)")
                
            time.sleep(0.5)
        
        # Verify results
        success_count = 0
        for job_id in job_ids:
            with get_db_session() as db:
                job = db.query(Job).filter(Job.id == job_id).first()
                if job and job.status == "done":
                    success_count += 1
                    print(f"✅ Job {job_id} completed successfully")
                elif job and job.status == "failed":
                    print(f"⚠️  Job {job_id} failed: {job.error_message}")
        
        success_rate = (success_count / len(job_ids)) * 100
        print(f"\n📊 Results: {success_count}/{len(job_ids)} jobs completed ({success_rate:.1f}%)")
        
        assert success_rate >= 80, f"Success rate {success_rate}% below 80%"
        
        return True
    except Exception as e:
        print(f"❌ End-to-end processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        if supervisor:
            supervisor.stop()
        if queue:
            queue.close()
        # Clean up test jobs from database
        if job_ids:
            try:
                with get_db_session() as db:
                    db.query(Job).filter(Job.id.in_(job_ids)).delete(synchronize_session=False)
                    db.commit()
            except Exception as e:
                print(f"⚠️  Warning: Failed to clean up test jobs: {e}")


def test_status_tracking():
    """Test 5: Job status tracking."""
    print("\n" + "="*80)
    print("TEST 5: Status Tracking")
    print("="*80)
    
    # Check database availability first
    if not check_database_available():
        print("⚠️  Skipping test: Database not available")
        print("   To run this test, ensure PostgreSQL is running and configured")
        print("   Check your database connection settings in .env or environment variables")
        return None  # Skip, don't fail
    
    job_id = None
    try:
        with get_db_session() as db:
            # Create a test job
            job_id = uuid4()
            request_id = str(uuid4())
            
            job = Job(
                id=job_id,
                request_id=request_id,
                job_type="json",
                status="queued",
                job_data={"test": "status"},
                asset_ids=[]
            )
            db.add(job)
            db.commit()
            
            print(f"✅ Created job {job_id} with status: {job.status}")
            
            # Update status
            job.status = "processing"
            job.started_at = datetime.utcnow()
            db.commit()
            print(f"✅ Updated status to: {job.status}")
            
            # Verify status
            job_check = db.query(Job).filter(Job.id == job_id).first()
            assert job_check.status == "processing", f"Expected 'processing', got '{job_check.status}'"
            print(f"✅ Status verified: {job_check.status}")
        
        return True
    except Exception as e:
        print(f"❌ Status tracking failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up test job
        if job_id:
            try:
                with get_db_session() as db:
                    db.query(Job).filter(Job.id == job_id).delete(synchronize_session=False)
                    db.commit()
            except Exception as e:
                print(f"⚠️  Warning: Failed to clean up test job: {e}")


def main():
    """Run all end-to-end tests."""
    print("="*80)
    print("END-TO-END TEST SUITE - Job Queue & Worker System")
    print("="*80)
    print(f"Started at: {datetime.now().isoformat()}\n")
    
    tests = [
        ("Redis Connection", test_redis_connection),
        ("Redis Queue Operations", test_redis_queue_operations),
        ("Redis Retry Logic", test_redis_retry_logic),
        ("End-to-End Processing", test_end_to_end_processing),
        ("Status Tracking", test_status_tracking),
    ]
    
    results = []
    skipped = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            if result is None:
                skipped.append(test_name)
                results.append((test_name, None))
            else:
                results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result is True)
    failed = sum(1 for _, result in results if result is False)
    skipped_count = sum(1 for _, result in results if result is None)
    total = len(results)
    
    for test_name, result in results:
        if result is None:
            status = "⏭️  SKIPPED"
        elif result:
            status = "✅ PASSED"
        else:
            status = "❌ FAILED"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    if skipped_count > 0:
        print(f"Skipped: {skipped_count} test(s)")
    if failed > 0:
        print(f"Failed: {failed} test(s)")
    print(f"Completed at: {datetime.now().isoformat()}")
    print("="*80)
    
    # Return 0 only if all non-skipped tests passed
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

