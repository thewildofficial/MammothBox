"""
Queue manager for application-wide queue access.

Provides singleton access to queue backend and worker supervisor.
"""

from typing import Optional

from src.queue.interface import QueueBackend
from src.queue.supervisor import WorkerSupervisor
from src.queue import create_queue_backend

# Global instances (initialized in main.py)
_queue_backend: Optional[QueueBackend] = None
_worker_supervisor: Optional[WorkerSupervisor] = None


def get_queue_backend() -> QueueBackend:
    """Get the global queue backend instance."""
    global _queue_backend
    if _queue_backend is None:
        _queue_backend = create_queue_backend()
    return _queue_backend


def get_worker_supervisor() -> Optional[WorkerSupervisor]:
    """Get the global worker supervisor instance."""
    return _worker_supervisor


def set_worker_supervisor(supervisor: WorkerSupervisor) -> None:
    """Set the global worker supervisor instance."""
    global _worker_supervisor
    _worker_supervisor = supervisor

