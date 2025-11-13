"""
Queue module for async job processing.

Provides queue backends (in-process, Redis) and factory function
for selecting the appropriate backend based on configuration.
"""

from src.config.settings import get_settings
from src.queue.interface import QueueBackend, QueueMessage, Acknowledgement
from src.queue.inproc import InProcessQueue
from src.queue.redis import RedisQueue


def create_queue_backend() -> QueueBackend:
    """
    Factory function to create queue backend based on settings.
    
    Returns:
        QueueBackend instance (InProcessQueue or RedisQueue)
    """
    settings = get_settings()
    
    if settings.queue_backend == "redis":
        return RedisQueue(redis_url=settings.redis_url)
    else:
        # Default to in-process queue
        return InProcessQueue(max_retries=3)


__all__ = [
    "QueueBackend",
    "QueueMessage",
    "Acknowledgement",
    "InProcessQueue",
    "RedisQueue",
    "create_queue_backend",
]

