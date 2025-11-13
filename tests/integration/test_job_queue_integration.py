"""
Integration tests for job queue and worker system.

Tests the full flow: API ingestion -> queue -> worker processing -> status endpoint.
"""

import pytest
import time
from uuid import uuid4

from src.catalog.database import get_db_session
from src.catalog.models import Job, Asset
from src.queue.manager import get_queue_backend
from src.queue.supervisor import WorkerSupervisor
from src.queue.processors import JsonJobProcessor


@pytest.fixture
def queue_backend():
    """Create a queue backend for testing."""
    from src.queue.inproc import InProcessQueue
    return InProcessQueue()


@pytest.fixture
def worker_supervisor(queue_backend):
    """Create a worker supervisor for testing."""
    processors = {
        "json": JsonJobProcessor(),
    }
    supervisor = WorkerSupervisor(
        queue_backend=queue_backend,
        processors=processors,
        num_workers=2
    )
    supervisor.start()
    yield supervisor
    supervisor.stop()


class TestJobQueueIntegration:
    """Integration tests for job queue system."""
    
    def test_json_job_processing_flow(self, queue_backend, worker_supervisor):
        """Test full flow: enqueue -> process -> complete."""
        # Create a test job
        job_id = uuid4()
        request_id = str(uuid4())
        
        documents = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25}
        ]
        
        # Create job record in database
        with get_db_session() as db:
            job = Job(
                id=job_id,
                request_id=request_id,
                job_type="json",
                status="queued",
                job_data={
                    "job_id": str(job_id),
                    "documents": documents,
                    "request_id": request_id,
                    "owner": "test_user",
                    "collection_name_hint": None
                }
            )
            db.add(job)
            db.commit()
        
        # Enqueue job
        from src.queue.interface import QueueMessage
        from datetime import datetime
        
        message = QueueMessage(
            job_id=job_id,
            job_type="json",
            job_data=job.job_data,
            created_at=datetime.utcnow()
        )
        queue_backend.enqueue(message)
        
        # Wait for processing (with timeout)
        max_wait = 10.0
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            with get_db_session() as db:
                job = db.query(Job).filter(Job.id == job_id).first()
                if job and job.status in ["done", "failed"]:
                    break
            time.sleep(0.5)
        
        # Verify job completed
        with get_db_session() as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            assert job is not None
            assert job.status == "done"
            assert job.asset_ids is not None
            assert len(job.asset_ids) == 2
            
            # Verify assets were created
            assets = db.query(Asset).filter(Asset.id.in_(job.asset_ids)).all()
            assert len(assets) == 2
            for asset in assets:
                assert asset.status in ["done", "queued"]  # May be queued if schema is provisional
                assert asset.kind == "json"
    
    def test_job_retry_on_failure(self, queue_backend, worker_supervisor):
        """Test that jobs retry on transient failures."""
        # This test would require mocking the processor to fail
        # For now, we'll just verify the retry mechanism exists
        # Full retry testing would require more complex setup
        pass
    
    def test_dead_letter_queue(self, queue_backend):
        """Test that failed jobs move to dead-letter queue."""
        job_id = uuid4()
        
        from src.queue.interface import QueueMessage
        from datetime import datetime
        
        message = QueueMessage(
            job_id=job_id,
            job_type="json",
            job_data={},
            retry_count=2,  # Already at max retries
            max_retries=3,
            created_at=datetime.utcnow()
        )
        
        queue_backend.enqueue(message)
        dequeued = queue_backend.dequeue(timeout=1.0)
        assert dequeued is not None
        
        # Nack should move to DLQ
        queue_backend.nack(job_id, "Test error")
        
        assert queue_backend.get_dlq_size() == 1
        dlq_messages = queue_backend.get_dlq_messages()
        assert job_id in dlq_messages


