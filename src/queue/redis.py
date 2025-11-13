"""
Redis queue backend (stub implementation for future scaling).

This is a placeholder for distributed queue support using Redis.
Currently raises NotImplementedError - to be implemented in future phases.
"""

from typing import Optional
from uuid import UUID

from src.queue.interface import QueueBackend, QueueMessage


class RedisQueue(QueueBackend):
    """
    Redis-backed queue backend (stub).
    
    Future implementation for distributed workers across multiple instances.
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        """
        Initialize Redis queue backend.
        
        Args:
            redis_url: Redis connection URL
        """
        self.redis_url = redis_url
        raise NotImplementedError(
            "Redis queue backend not yet implemented. "
            "Use 'inproc' backend for MVP."
        )
    
    def enqueue(self, message: QueueMessage) -> None:
        """Add a job to the queue."""
        raise NotImplementedError()
    
    def dequeue(self, timeout: Optional[float] = None) -> Optional[QueueMessage]:
        """Get the next job from the queue."""
        raise NotImplementedError()
    
    def ack(self, job_id: UUID) -> None:
        """Acknowledge successful job completion."""
        raise NotImplementedError()
    
    def nack(self, job_id: UUID, error: str) -> None:
        """Handle job failure."""
        raise NotImplementedError()
    
    def size(self) -> int:
        """Get current queue size."""
        raise NotImplementedError()
    
    def close(self) -> None:
        """Close the queue backend."""
        raise NotImplementedError()

