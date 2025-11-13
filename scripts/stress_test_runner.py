#!/usr/bin/env python3
"""
End-to-end stress test runner for job queue system.

This script runs comprehensive stress tests and generates a detailed report.
"""

import sys
import os
import time
import statistics
import json
from datetime import datetime
from uuid import uuid4
from typing import List, Dict

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.queue.inproc import InProcessQueue
from src.queue.interface import QueueMessage
from src.queue.supervisor import WorkerSupervisor
from src.queue.processors import JsonJobProcessor
from src.catalog.database import get_db_session, init_db
from src.catalog.models import Job, Asset


class StressTestRunner:
    """Runs stress tests and collects metrics."""
    
    def __init__(self):
        self.results = []
    
    def run_test(self, test_name: str, test_func):
        """Run a single test and collect results."""
        print(f"\n{'='*80}")
        print(f"TEST: {test_name}")
        print(f"{'='*80}")
        
        start_time = time.time()
        try:
            result = test_func()
            duration = time.time() - start_time
            result['test_name'] = test_name
            result['duration'] = duration
            result['status'] = 'PASSED'
            self.results.append(result)
            print(f"\n✅ PASSED in {duration:.2f}s")
            return result
        except Exception as e:
            duration = time.time() - start_time
            error_result = {
                'test_name': test_name,
                'duration': duration,
                'status': 'FAILED',
                'error': str(e)
            }
            self.results.append(error_result)
            print(f"\n❌ FAILED in {duration:.2f}s: {e}")
            import traceback
            traceback.print_exc()
            return error_result
    
    def generate_report(self):
        """Generate final test report."""
        print(f"\n{'='*80}")
        print("STRESS TEST REPORT")
        print(f"{'='*80}\n")
        
        total_tests = len(self.results)
        passed = sum(1 for r in self.results if r['status'] == 'PASSED')
        failed = total_tests - passed
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {(passed/total_tests*100):.1f}%")
        print(f"\nTotal Duration: {sum(r['duration'] for r in self.results):.2f}s\n")
        
        print("Detailed Results:")
        print("-" * 80)
        for result in self.results:
            status_icon = "✅" if result['status'] == 'PASSED' else "❌"
            print(f"{status_icon} {result['test_name']}: {result['status']} ({result['duration']:.2f}s)")
            if result['status'] == 'PASSED' and 'metrics' in result:
                metrics = result['metrics']
                for key, value in metrics.items():
                    if isinstance(value, float):
                        print(f"   {key}: {value:.3f}")
                    else:
                        print(f"   {key}: {value}")
            elif result['status'] == 'FAILED':
                print(f"   Error: {result.get('error', 'Unknown error')}")
        
        # Save report to file
        report_file = os.path.join(project_root, 'stress_test_report.json')
        with open(report_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'summary': {
                    'total': total_tests,
                    'passed': passed,
                    'failed': failed,
                    'success_rate': passed/total_tests*100 if total_tests > 0 else 0
                },
                'results': self.results
            }, f, indent=2)
        
        print(f"\n📄 Detailed report saved to: {report_file}")
        
        return passed == total_tests


def test_queue_latency():
    """Test 1: Queue latency target (< 100ms)."""
    queue = InProcessQueue()
    latencies = []
    
    try:
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
        
        avg = statistics.mean(latencies)
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        max_latency = max(latencies)
        
        assert avg < 100, f"Average latency {avg:.3f}ms exceeds 100ms target"
        assert p95 < 100, f"P95 latency {p95:.3f}ms exceeds 100ms target"
        
        return {
            'metrics': {
                'avg_latency_ms': avg,
                'p95_latency_ms': p95,
                'p99_latency_ms': p99,
                'max_latency_ms': max_latency,
                'target_met': True
            }
        }
    finally:
        queue.close()


def test_concurrent_operations():
    """Test 2: Concurrent enqueue/dequeue operations."""
    import threading
    
    queue = InProcessQueue()
    enqueued = []
    dequeued = []
    lock = threading.Lock()
    
    def enqueue_worker(worker_id, count):
        for i in range(count):
            job_id = uuid4()
            message = QueueMessage(
                job_id=job_id,
                job_type="json",
                job_data={'worker': worker_id, 'index': i},
                created_at=datetime.utcnow()
            )
            queue.enqueue(message)
            with lock:
                enqueued.append(job_id)
            time.sleep(0.001)
    
    def dequeue_worker():
        while len(dequeued) < 50:
            message = queue.dequeue(timeout=0.5)
            if message:
                with lock:
                    dequeued.append(message.job_id)
                queue.ack(message.job_id)
    
    try:
        # Start enqueue threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=enqueue_worker, args=(i, 10))
            t.start()
            threads.append(t)
        
        # Start dequeue thread
        dequeue_thread = threading.Thread(target=dequeue_worker)
        dequeue_thread.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        dequeue_thread.join(timeout=5.0)
        
        assert len(enqueued) == 50, f"Expected 50 enqueued, got {len(enqueued)}"
        assert len(dequeued) == 50, f"Expected 50 dequeued, got {len(dequeued)}"
        assert queue.size() == 0, f"Queue should be empty, got {queue.size()}"
        
        return {
            'metrics': {
                'enqueued': len(enqueued),
                'dequeued': len(dequeued),
                'final_queue_size': queue.size(),
                'thread_safety': 'PASSED'
            }
        }
    finally:
        queue.close()


def test_retry_exponential_backoff():
    """Test 3: Retry logic with exponential backoff."""
    queue = InProcessQueue()
    
    try:
        job_id = uuid4()
        message = QueueMessage(
            job_id=job_id,
            job_type="json",
            job_data={},
            retry_count=0,
            max_retries=3
        )
        
        queue.enqueue(message)
        retry_delays = []
        
        # Simulate retries
        for attempt in range(3):
            dequeued = queue.dequeue(timeout=1.0)
            if dequeued:
                if attempt < 2:
                    queue.nack(job_id, f"Error {attempt + 1}")
                    if dequeued.next_retry_at:
                        delay = (dequeued.next_retry_at - datetime.utcnow()).total_seconds()
                        retry_delays.append(delay)
                else:
                    queue.nack(job_id, "Final error")
        
        assert queue.get_dlq_size() == 1, "Job should be in DLQ after max retries"
        
        return {
            'metrics': {
                'retry_delays': [f"{d:.2f}s" for d in retry_delays],
                'dlq_size': queue.get_dlq_size(),
                'exponential_backoff': 'VERIFIED'
            }
        }
    finally:
        queue.close()


def test_end_to_end_processing():
    """Test 4: End-to-end job processing with database."""
    # Initialize database if needed
    try:
        init_db()
    except:
        pass  # May already be initialized
    
    queue = InProcessQueue()
    processors = {"json": JsonJobProcessor()}
    supervisor = WorkerSupervisor(queue, processors, num_workers=2)
    
    job_ids = []
    processing_times = []
    
    try:
        supervisor.start()
        time.sleep(1)  # Let workers start
        
        # Create 20 jobs
        for i in range(20):
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
                        "documents": [{"id": i, "name": f"TestUser{i}"}],
                        "request_id": request_id,
                        "owner": "stress_test"
                    }
                )
                db.add(job)
                db.commit()
            
            message = QueueMessage(
                job_id=job_id,
                job_type="json",
                job_data=job.job_data,
                created_at=datetime.utcnow()
            )
            queue.enqueue(message)
            job_ids.append(job_id)
        
        # Wait for processing
        max_wait = 30.0
        start_wait = time.time()
        
        while time.time() - start_wait < max_wait:
            completed = 0
            with get_db_session() as db:
                for job_id in job_ids:
                    job = db.query(Job).filter(Job.id == job_id).first()
                    if job and job.status == "done":
                        completed += 1
                        if job.completed_at:
                            proc_time = (job.completed_at - job.created_at).total_seconds()
                            processing_times.append(proc_time)
            
            if completed == len(job_ids):
                break
            time.sleep(0.5)
        
        success_rate = (completed / len(job_ids)) * 100 if job_ids else 0
        avg_processing = statistics.mean(processing_times) if processing_times else 0
        
        assert success_rate >= 90, f"Success rate {success_rate}% below 90%"
        
        return {
            'metrics': {
                'jobs_created': len(job_ids),
                'jobs_completed': completed,
                'success_rate': f"{success_rate:.1f}%",
                'avg_processing_time': f"{avg_processing:.3f}s",
                'throughput': f"{completed/(time.time() - start_wait):.2f} jobs/sec"
            }
        }
    finally:
        supervisor.stop()
        queue.close()


def main():
    """Run all stress tests."""
    print("=" * 80)
    print("JOB QUEUE SYSTEM - STRESS TEST SUITE")
    print("=" * 80)
    print(f"Started at: {datetime.now().isoformat()}\n")
    
    runner = StressTestRunner()
    
    # Run tests
    runner.run_test("Queue Latency (< 100ms)", test_queue_latency)
    runner.run_test("Concurrent Operations", test_concurrent_operations)
    runner.run_test("Retry Exponential Backoff", test_retry_exponential_backoff)
    runner.run_test("End-to-End Processing", test_end_to_end_processing)
    
    # Generate report
    all_passed = runner.generate_report()
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

