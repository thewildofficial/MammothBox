"""
In-process queue backend using Python's queue.PriorityQueue.

Thread-safe implementation for MVP that handles retry delays and
dead-letter queue assignment without external dependencies.
"""

import queue
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Dict
from uuid import UUID

from src.queue.interface import QueueBackend, QueueMessage, Acknowledgement


class InProcessQueue(QueueBackend):
    """
    In-process priority queue backend.
    
    Uses Python's PriorityQueue for thread-safe job processing.
    Supports priority ordering, retry delays, and dead-letter queue.
    """
    
    def __init__(self, max_retries: int = 3):
        """
        Initialize in-process queue.
        
        Args:
            max_retries: Maximum retry attempts before moving to DLQ
        """
        self._queue = queue.PriorityQueue()
        self._processing: Dict[UUID, QueueMessage] = {}
        self._dead_letter_queue: Dict[UUID, QueueMessage] = {}
        self._lock = threading.Lock()
        self._max_retries = max_retries
        self._closed = False
    
    def enqueue(self, message: QueueMessage) -> None:
        """Add a job to the queue."""
        if self._closed:
            raise RuntimeError("Queue is closed")
        
        # Priority queue uses tuple (priority, timestamp, message)
        # Lower priority number = higher priority (processed first)
        priority_tuple = (-message.priority, message.created_at.timestamp(), message)
        self._queue.put(priority_tuple)
    
    def dequeue(self, timeout: Optional[float] = None) -> Optional[QueueMessage]:
        """
        Get the next job from the queue.
        
        Handles retry delays by checking next_retry_at timestamp.
        """
        if self._closed:
            return None
        
        deadline = time.time() + timeout if timeout else None
        
        while True:
            # Check if we've exceeded timeout
            if deadline and time.time() >= deadline:
                return None
            
            try:
                # Get next message (non-blocking if timeout specified)
                remaining_timeout = deadline - time.time() if deadline else None
                if remaining_timeout and remaining_timeout <= 0:
                    return None
                
                priority_tuple = self._queue.get(timeout=min(remaining_timeout or 0.1, 0.1))
                _, _, message = priority_tuple
                
                # Check if this message is ready for retry
                if message.next_retry_at and message.next_retry_at > datetime.utcnow():
                    # Not ready yet, put it back
                    self._queue.put(priority_tuple)
                    # Sleep briefly before checking again
                    time.sleep(0.1)
                    continue
                
                # Mark as processing
                with self._lock:
                    self._processing[message.job_id] = message
                
                return message
                
            except queue.Empty:
                # No messages available, check timeout
                if deadline and time.time() >= deadline:
                    return None
                # Continue waiting
                continue
    
    def ack(self, job_id: UUID) -> None:
        """Acknowledge successful job completion."""
        with self._lock:
            if job_id in self._processing:
                del self._processing[job_id]
    
    def nack(self, job_id: UUID, error: str) -> None:
        """
        Handle job failure with retry logic.
        
        If retry count < max_retries, schedules retry with exponential backoff.
        Otherwise, moves to dead-letter queue.
        """
        with self._lock:
            if job_id not in self._processing:
                return
            
            message = self._processing[job_id]
            del self._processing[job_id]
            
            # Check if we should retry
            if message.retry_count < message.max_retries:
                # Exponential backoff: 2^retry_count seconds
                backoff_seconds = 2 ** message.retry_count
                message.retry_count += 1
                message.next_retry_at = datetime.utcnow() + timedelta(seconds=backoff_seconds)
                
                # Re-enqueue with updated retry info
                priority_tuple = (-message.priority, message.created_at.timestamp(), message)
                self._queue.put(priority_tuple)
            else:
                # Max retries exceeded, move to dead-letter queue
                message.next_retry_at = None
                self._dead_letter_queue[job_id] = message
    
    def size(self) -> int:
        """Get current queue size (excluding processing and DLQ)."""
        return self._queue.qsize()
    
    def get_dlq_size(self) -> int:
        """Get dead-letter queue size."""
        with self._lock:
            return len(self._dead_letter_queue)
    
    def get_dlq_messages(self) -> Dict[UUID, QueueMessage]:
        """Get all dead-letter queue messages."""
        with self._lock:
            return self._dead_letter_queue.copy()
    
    def close(self) -> None:
        """Close the queue backend."""
        self._closed = True
        # Drain remaining messages
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

