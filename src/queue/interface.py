"""
Queue interface for job processing.

Defines the abstract interface for queue backends (in-process, Redis, etc.)
to enable async job processing with retry and dead-letter queue support.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID


@dataclass
class QueueMessage:
    """Represents a message in the queue."""
    job_id: UUID
    job_type: str  # 'media' or 'json'
    job_data: Dict[str, Any]
    priority: int = 0  # Higher priority = processed first
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: Optional[datetime] = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


@dataclass
class Acknowledgement:
    """Acknowledgement result for job processing."""
    job_id: UUID
    success: bool
    error_message: Optional[str] = None


class QueueBackend(ABC):
    """
    Abstract base class for queue backends.
    
    All queue implementations must provide these methods for
    enqueueing, dequeuing, and acknowledging jobs.
    """
    
    @abstractmethod
    def enqueue(self, message: QueueMessage) -> None:
        """
        Add a job to the queue.
        
        Args:
            message: Queue message to enqueue
        """
        pass
    
    @abstractmethod
    def dequeue(self, timeout: Optional[float] = None) -> Optional[QueueMessage]:
        """
        Get the next job from the queue.
        
        Args:
            timeout: Optional timeout in seconds (None = block indefinitely)
            
        Returns:
            QueueMessage if available, None if timeout
        """
        pass
    
    @abstractmethod
    def ack(self, job_id: UUID) -> None:
        """
        Acknowledge successful job completion.
        
        Args:
            job_id: Job identifier to acknowledge
        """
        pass
    
    @abstractmethod
    def nack(self, job_id: UUID, error: str) -> None:
        """
        Handle job failure (negative acknowledgement).
        
        Args:
            job_id: Job identifier that failed
            error: Error message describing the failure
        """
        pass
    
    @abstractmethod
    def size(self) -> int:
        """
        Get the current queue size.
        
        Returns:
            Number of jobs in queue
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close the queue backend and cleanup resources."""
        pass


