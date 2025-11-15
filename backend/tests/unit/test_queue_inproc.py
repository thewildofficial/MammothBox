"""
Unit tests for in-process queue backend.
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from src.queue.inproc import InProcessQueue
from src.queue.interface import QueueMessage


class TestInProcessQueue:
    """Test in-process queue backend."""
    
    def test_enqueue_dequeue(self):
        """Test basic enqueue and dequeue."""
        queue = InProcessQueue()
        
        job_id = uuid4()
        message = QueueMessage(
            job_id=job_id,
            job_type="json",
            job_data={"test": "data"},
            priority=0
        )
        
        queue.enqueue(message)
        assert queue.size() == 1
        
        dequeued = queue.dequeue(timeout=1.0)
        assert dequeued is not None
        assert dequeued.job_id == job_id
        assert queue.size() == 0
    
    def test_priority_ordering(self):
        """Test that higher priority jobs are dequeued first."""
        queue = InProcessQueue()
        
        # Enqueue low priority first
        low_priority = QueueMessage(
            job_id=uuid4(),
            job_type="json",
            job_data={},
            priority=0
        )
        queue.enqueue(low_priority)
        
        # Enqueue high priority
        high_priority = QueueMessage(
            job_id=uuid4(),
            job_type="json",
            job_data={},
            priority=10
        )
        queue.enqueue(high_priority)
        
        # High priority should be dequeued first
        first = queue.dequeue(timeout=1.0)
        assert first.priority == 10
        
        second = queue.dequeue(timeout=1.0)
        assert second.priority == 0
    
    def test_ack(self):
        """Test job acknowledgement."""
        queue = InProcessQueue()
        
        job_id = uuid4()
        message = QueueMessage(
            job_id=job_id,
            job_type="json",
            job_data={}
        )
        
        queue.enqueue(message)
        dequeued = queue.dequeue(timeout=1.0)
        assert dequeued is not None
        
        queue.ack(job_id)
        # After ack, job should be removed from processing
        assert job_id not in queue._processing
    
    def test_nack_retry(self):
        """Test negative acknowledgement with retry."""
        queue = InProcessQueue()
        
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
        assert dequeued is not None
        
        # Nack should schedule retry
        queue.nack(job_id, "Test error")
        
        # Job should be re-enqueued with updated retry count
        assert queue.size() == 1
        
        # The retried job has a future next_retry_at, so we need to check
        # by looking at what's in the queue (it won't dequeue until retry time)
        # Instead, verify the queue has the job and check DLQ is empty
        assert queue.get_dlq_size() == 0  # Should not be in DLQ yet
        
        # Manually check the queue contents by trying to peek
        # Since we can't peek, we'll verify by checking that after retry delay
        # the job can be dequeued. For now, just verify it's re-enqueued.
        import time
        time.sleep(2)  # Wait for retry delay (2^0 = 1 second)
        retried = queue.dequeue(timeout=1.0)
        assert retried is not None
        assert retried.retry_count == 1
        assert retried.next_retry_at is not None
    
    def test_nack_dead_letter(self):
        """Test that max retries moves job to dead-letter queue."""
        queue = InProcessQueue()
        
        job_id = uuid4()
        # Set retry_count to max_retries so next nack goes to DLQ
        message = QueueMessage(
            job_id=job_id,
            job_type="json",
            job_data={},
            retry_count=3,  # Equal to max_retries, so next nack goes to DLQ
            max_retries=3
        )
        
        queue.enqueue(message)
        dequeued = queue.dequeue(timeout=1.0)
        assert dequeued is not None
        
        # Nack should move to DLQ after max retries exceeded
        queue.nack(job_id, "Final error")
        
        assert queue.size() == 0
        assert queue.get_dlq_size() == 1
        dlq_messages = queue.get_dlq_messages()
        assert job_id in dlq_messages
    
    def test_retry_delay(self):
        """Test that retried jobs respect next_retry_at delay."""
        queue = InProcessQueue()
        
        job_id = uuid4()
        message = QueueMessage(
            job_id=job_id,
            job_type="json",
            job_data={},
            retry_count=0,
            max_retries=3,
            next_retry_at=datetime.utcnow() + timedelta(seconds=10)
        )
        
        queue.enqueue(message)
        
        # Should not dequeue immediately (future retry time)
        dequeued = queue.dequeue(timeout=0.1)
        assert dequeued is None  # Should timeout
    
    def test_close(self):
        """Test queue closure."""
        queue = InProcessQueue()
        
        message = QueueMessage(
            job_id=uuid4(),
            job_type="json",
            job_data={}
        )
        queue.enqueue(message)
        
        queue.close()
        
        # Should not accept new jobs
        with pytest.raises(RuntimeError):
            queue.enqueue(message)
        
        # Should not dequeue
        assert queue.dequeue(timeout=0.1) is None

