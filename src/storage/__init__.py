"""
Storage backend abstraction for file operations.

Provides adapters for filesystem and S3 storage backends.
"""

from src.storage.adapter import StorageAdapter, StorageError
from src.storage.filesystem import FilesystemStorage
from src.storage.factory import get_storage_adapter, reset_storage_adapter

__all__ = [
    "StorageAdapter",
    "StorageError",
    "FilesystemStorage",
    "get_storage_adapter",
    "reset_storage_adapter",
]
