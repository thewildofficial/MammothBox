"""
Comprehensive stress tests for job queue system.

Tests high-volume scenarios, concurrent processing, retry logic,
dead-letter queue, and system resilience.
"""

import pytest
import time
import threading
import statistics
from datetime import datetime
from uuid import uuid4
from typing import List, Dict
import json

from src.catalog.database import get_db_session
from src.catalog.models import Job, Asset
from src.queue.inproc import InProcessQueue
from src.queue.interface import QueueMessage
from src.queue.supervisor import WorkerSupervisor
from src.queue.processors import JsonJobProcessor


class StressTestResults:
    """Container for stress test results."""
    
    def __init__(self):
        self.jobs_created = 0
        self.jobs_completed = 0
        self.jobs_failed = 0
        self.jobs_dlq = 0
        self.processing_times = []
        self.queue_latencies = []
        self.worker_pickup_times = []
        self.errors = []
        self.start_time = None
        self.end_time = None
    
    def record_job_created(self):
        self.jobs_created += 1
    
    def record_job_completed(self, processing_time: float):
        self.jobs_completed += 1
        self.processing_times.append(processing_time)
    
    def record_job_failed(self):
        self.jobs_failed += 1
    
    def record_job_dlq(self):
        self.jobs_dlq += 1
    
    def record_queue_latency(self, latency: float):
        self.queue_latencies.append(latency)
    
    def record_worker_pickup(self, pickup_time: float):
        self.worker_pickup_times.append(pickup_time)
    
    def record_error(self, error: str):
        self.errors.append(error)
    
    def get_summary(self) -> Dict:
        """Get summary statistics."""
        return {
            "total_jobs": self.jobs_created,
            "completed": self.jobs_completed,
            "failed": self.jobs_failed,
            "dead_letter": self.jobs_dlq,
            "success_rate": (self.jobs_completed / self.jobs_created * 100) if self.jobs_created > 0 else 0,
            "avg_processing_time": statistics.mean(self.processing_times) if self.processing_times else 0,
            "median_processing_time": statistics.median(self.processing_times) if self.processing_times else 0,
            "p95_processing_time": self._percentile(self.processing_times, 95) if self.processing_times else 0,
            "p99_processing_time": self._percentile(self.processing_times, 99) if self.processing_times else 0,
            "avg_queue_latency": statistics.mean(self.queue_latencies) if self.queue_latencies else 0,
            "avg_worker_pickup": statistics.mean(self.worker_pickup_times) if self.worker_pickup_times else 0,
            "total_errors": len(self.errors),
            "duration_seconds": (self.end_time - self.start_time).total_seconds() if self.end_time and self.start_time else 0,
            "throughput_jobs_per_sec": self.jobs_completed / ((self.end_time - self.start_time).total_seconds()) if self.end_time and self.start_time and (self.end_time - self.start_time).total_seconds() > 0 else 0
        }
    
    @staticmethod
    def _percentile(data: List[float], percentile: int) -> float:
        """Calculate percentile."""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]


class TestQueueStress:
    """Stress tests for queue system."""
    
    def test_high_volume_processing(self):
        """Test processing 100 jobs concurrently."""
        print("\n=== Test 1: High Volume Processing (100 jobs) ===")
        
        queue = InProcessQueue()
        processors = {"json": JsonJobProcessor()}
        supervisor = WorkerSupervisor(queue, processors, num_workers=4)
        supervisor.start()
        
        results = StressTestResults()
        results.start_time = datetime.utcnow()
        
        try:
            # Create 100 jobs
            job_ids = []
            for i in range(100):
                job_id = uuid4()
                request_id = str(uuid4())
                
                # Create job in database
                with get_db_session() as db:
                    job = Job(
                        id=job_id,
                        request_id=request_id,
                        job_type="json",
                        status="queued",
                        job_data={
                            "job_id": str(job_id),
                            "documents": [{"id": i, "name": f"User{i}", "value": i * 10}],
                            "request_id": request_id,
                            "owner": "stress_test"
                        }
                    )
                    db.add(job)
                    db.commit()
                
                # Enqueue
                enqueue_start = time.time()
                message = QueueMessage(
                    job_id=job_id,
                    job_type="json",
                    job_data=job.job_data,
                    created_at=datetime.utcnow()
                )
                queue.enqueue(message)
                queue_latency = (time.time() - enqueue_start) * 1000  # ms
                results.record_queue_latency(queue_latency)
                results.record_job_created()
                job_ids.append(job_id)
            
            print(f"Created {len(job_ids)} jobs, waiting for processing...")
            
            # Wait for all jobs to complete (with timeout)
            max_wait = 60.0
            start_wait = time.time()
            
            while time.time() - start_wait < max_wait:
                completed = 0
                failed = 0
                dlq = 0
                
                with get_db_session() as db:
                    for job_id in job_ids:
                        job = db.query(Job).filter(Job.id == job_id).first()
                        if job:
                            if job.status == "done":
                                completed += 1
                            elif job.status == "failed":
                                failed += 1
                            if job.dead_letter:
                                dlq += 1
                
                if completed + failed == len(job_ids):
                    break
                
                time.sleep(0.5)
            
            # Collect final results
            for job_id in job_ids:
                with get_db_session() as db:
                    job = db.query(Job).filter(Job.id == job_id).first()
                    if job:
                        if job.status == "done":
                            processing_time = (job.completed_at - job.created_at).total_seconds() if job.completed_at else 0
                            results.record_job_completed(processing_time)
                        elif job.status == "failed":
                            results.record_job_failed()
                        if job.dead_letter:
                            results.record_job_dlq()
            
            results.end_time = datetime.utcnow()
            summary = results.get_summary()
            
            print(f"\nResults:")
            print(f"  Total Jobs: {summary['total_jobs']}")
            print(f"  Completed: {summary['completed']}")
            print(f"  Failed: {summary['failed']}")
            print(f"  Success Rate: {summary['success_rate']:.2f}%")
            print(f"  Avg Processing Time: {summary['avg_processing_time']:.3f}s")
            print(f"  P95 Processing Time: {summary['p95_processing_time']:.3f}s")
            print(f"  Avg Queue Latency: {summary['avg_queue_latency']:.3f}ms")
            print(f"  Throughput: {summary['throughput_jobs_per_sec']:.2f} jobs/sec")
            print(f"  Total Duration: {summary['duration_seconds']:.2f}s")
            
            # Assertions
            assert summary['success_rate'] >= 95, f"Success rate {summary['success_rate']}% below 95%"
            assert summary['avg_queue_latency'] < 100, f"Queue latency {summary['avg_queue_latency']}ms exceeds 100ms target"
            assert summary['throughput_jobs_per_sec'] > 1, f"Throughput {summary['throughput_jobs_per_sec']} too low"
            
        finally:
            supervisor.stop()
            queue.close()
    
    def test_concurrent_enqueue_dequeue(self):
        """Test concurrent enqueue/dequeue operations."""
        print("\n=== Test 2: Concurrent Enqueue/Dequeue ===")
        
        queue = InProcessQueue()
        results = StressTestResults()
        results.start_time = datetime.utcnow()
        
        enqueued = []
        dequeued = []
        lock = threading.Lock()
        
        def enqueue_worker(worker_id: int, count: int):
            for i in range(count):
                job_id = uuid4()
                message = QueueMessage(
                    job_id=job_id,
                    job_type="json",
                    job_data={"worker": worker_id, "index": i},
                    created_at=datetime.utcnow()
                )
                queue.enqueue(message)
                with lock:
                    enqueued.append(job_id)
                time.sleep(0.001)  # Small delay
        
        def dequeue_worker():
            while len(dequeued) < 50:  # Dequeue 50 messages
                message = queue.dequeue(timeout=0.1)
                if message:
                    with lock:
                        dequeued.append(message.job_id)
                    queue.ack(message.job_id)
        
        # Start enqueue threads
        enqueue_threads = []
        for i in range(5):
            thread = threading.Thread(target=enqueue_worker, args=(i, 10))
            thread.start()
            enqueue_threads.append(thread)
        
        # Start dequeue thread
        dequeue_thread = threading.Thread(target=dequeue_worker)
        dequeue_thread.start()
        
        # Wait for completion
        for thread in enqueue_threads:
            thread.join()
        dequeue_thread.join(timeout=5.0)
        
        results.end_time = datetime.utcnow()
        
        print(f"Enqueued: {len(enqueued)}")
        print(f"Dequeued: {len(dequeued)}")
        print(f"Queue Size: {queue.size()}")
        
        assert len(enqueued) == 50, f"Expected 50 enqueued, got {len(enqueued)}"
        assert len(dequeued) == 50, f"Expected 50 dequeued, got {len(dequeued)}"
        assert queue.size() == 0, f"Queue should be empty, got {queue.size()}"
        
        queue.close()
    
    def test_retry_logic(self):
        """Test retry mechanism with exponential backoff."""
        print("\n=== Test 3: Retry Logic ===")
        
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
        
        # Dequeue and nack multiple times
        retry_times = []
        for attempt in range(3):
            dequeued = queue.dequeue(timeout=1.0)
            assert dequeued is not None, f"Failed to dequeue on attempt {attempt + 1}"
            
            if attempt < 2:  # Don't nack on last attempt
                before_nack = time.time()
                queue.nack(job_id, f"Test error {attempt + 1}")
                
                # Check retry delay
                if dequeued.next_retry_at:
                    delay = (dequeued.next_retry_at - datetime.utcnow()).total_seconds()
                    retry_times.append(delay)
                    print(f"Attempt {attempt + 1}: Retry delay = {delay:.2f}s")
        
        # Final nack should move to DLQ
        dequeued = queue.dequeue(timeout=1.0)
        if dequeued:
            queue.nack(job_id, "Final error")
        
        assert queue.get_dlq_size() == 1, "Job should be in dead-letter queue"
        assert len(retry_times) == 2, f"Expected 2 retry delays, got {len(retry_times)}"
        
        # Verify exponential backoff (approximately 1s, 2s)
        assert 0.5 <= retry_times[0] <= 2.0, f"First retry delay {retry_times[0]} not in expected range"
        assert 1.0 <= retry_times[1] <= 4.0, f"Second retry delay {retry_times[1]} not in expected range"
        
        print("Retry logic verified: exponential backoff working correctly")
        queue.close()
    
    def test_worker_crash_recovery(self):
        """Test that system continues when workers encounter errors."""
        print("\n=== Test 4: Worker Crash Recovery ===")
        
        queue = InProcessQueue()
        
        # Create a processor that fails sometimes
        class FailingProcessor(JsonJobProcessor):
            call_count = 0
            
            def process(self, job_data: dict, db):
                FailingProcessor.call_count += 1
                if FailingProcessor.call_count <= 2:
                    raise Exception("Simulated failure")
                return super().process(job_data, db)
        
        processors = {"json": FailingProcessor()}
        supervisor = WorkerSupervisor(queue, processors, num_workers=2)
        supervisor.start()
        
        try:
            # Create job that will fail twice then succeed
            job_id = uuid4()
            request_id = str(uuid4())
            
            with get_db_session() as db:
                job = Job(
                    id=job_id,
                    request_id=request_id,
                    job_type="json",
                    status="queued",
                    job_data={
                        "job_id": str(job_id),
                        "documents": [{"test": "data"}],
                        "request_id": request_id
                    },
                    max_retries=3
                )
                db.add(job)
                db.commit()
            
            message = QueueMessage(
                job_id=job_id,
                job_type="json",
                job_data=job.job_data,
                max_retries=3,
                created_at=datetime.utcnow()
            )
            queue.enqueue(message)
            
            # Wait for processing
            max_wait = 30.0
            start = time.time()
            
            while time.time() - start < max_wait:
                with get_db_session() as db:
                    job = db.query(Job).filter(Job.id == job_id).first()
                    if job and job.status in ["done", "failed"]:
                        break
                time.sleep(0.5)
            
            # Verify job eventually succeeded after retries
            with get_db_session() as db:
                job = db.query(Job).filter(Job.id == job_id).first()
                assert job is not None
                assert job.status == "done", f"Job should succeed after retries, got {job.status}"
                assert job.retry_count >= 2, f"Job should have retried at least twice, got {job.retry_count}"
            
            print("Worker crash recovery verified: job succeeded after retries")
            
        finally:
            supervisor.stop()
            queue.close()
    
    def test_queue_latency_target(self):
        """Test that queue latency meets < 100ms target."""
        print("\n=== Test 5: Queue Latency Target (< 100ms) ===")
        
        queue = InProcessQueue()
        latencies = []
        
        for i in range(100):
            start = time.time()
            message = QueueMessage(
                job_id=uuid4(),
                job_type="json",
                job_data={},
                created_at=datetime.utcnow()
            )
            queue.enqueue(message)
            latency = (time.time() - start) * 1000  # ms
            latencies.append(latency)
        
        avg_latency = statistics.mean(latencies)
        p95_latency = StressTestResults._percentile(latencies, 95)
        p99_latency = StressTestResults._percentile(latencies, 95)
        
        print(f"Average Latency: {avg_latency:.3f}ms")
        print(f"P95 Latency: {p95_latency:.3f}ms")
        print(f"P99 Latency: {p99_latency:.3f}ms")
        
        assert avg_latency < 100, f"Average latency {avg_latency}ms exceeds 100ms target"
        assert p95_latency < 100, f"P95 latency {p95_latency}ms exceeds 100ms target"
        
        queue.close()
    
    def test_worker_pickup_time(self):
        """Test that worker pickup time meets < 1s target."""
        print("\n=== Test 6: Worker Pickup Time (< 1s) ===")
        
        queue = InProcessQueue()
        processors = {"json": JsonJobProcessor()}
        supervisor = WorkerSupervisor(queue, processors, num_workers=1)
        supervisor.start()
        
        pickup_times = []
        
        try:
            for i in range(10):
                job_id = uuid4()
                request_id = str(uuid4())
                
                with get_db_session() as db:
                    job = Job(
                        id=job_id,
                        request_id=request_id,
                        job_type="json",
                        status="queued",
                        job_data={
                            "job_id": str(job_id),
                            "documents": [{"id": i}],
                            "request_id": request_id
                        }
                    )
                    db.add(job)
                    db.commit()
                
                enqueue_time = time.time()
                message = QueueMessage(
                    job_id=job_id,
                    job_type="json",
                    job_data=job.job_data,
                    created_at=datetime.utcnow()
                )
                queue.enqueue(message)
                
                # Wait for job to be picked up (status changes to processing)
                max_wait = 5.0
                start_wait = time.time()
                
                while time.time() - start_wait < max_wait:
                    with get_db_session() as db:
                        job = db.query(Job).filter(Job.id == job_id).first()
                        if job and job.status == "processing":
                            pickup_time = time.time() - enqueue_time
                            pickup_times.append(pickup_time)
                            break
                    time.sleep(0.1)
                
                # Wait for completion before next job
                while time.time() - start_wait < max_wait:
                    with get_db_session() as db:
                        job = db.query(Job).filter(Job.id == job_id).first()
                        if job and job.status == "done":
                            break
                    time.sleep(0.1)
            
            avg_pickup = statistics.mean(pickup_times)
            p95_pickup = StressTestResults._percentile(pickup_times, 95)
            
            print(f"Average Pickup Time: {avg_pickup:.3f}s")
            print(f"P95 Pickup Time: {p95_pickup:.3f}s")
            
            assert avg_pickup < 1.0, f"Average pickup time {avg_pickup}s exceeds 1s target"
            
        finally:
            supervisor.stop()
            queue.close()

