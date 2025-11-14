"""
Storage factory for creating storage adapter instances.

Provides singleton access to storage backends based on configuration.
"""

from functools import lru_cache
from typing import Optional

from src.config.settings import get_settings
from src.storage.adapter import StorageAdapter
from src.storage.filesystem import FilesystemStorage


_storage_instance: Optional[StorageAdapter] = None


@lru_cache()
def get_storage_adapter() -> StorageAdapter:
    """
    Get or create the storage adapter instance.
    
    Returns:
        StorageAdapter instance (FilesystemStorage)
    """
    global _storage_instance
    
    if _storage_instance is None:
        settings = get_settings()
        # Use filesystem storage
            _storage_instance = FilesystemStorage(base_path=settings.storage_path)
    
    return _storage_instance


def reset_storage_adapter() -> None:
    """Reset the storage adapter instance (useful for testing)."""
    global _storage_instance
    _storage_instance = None
    get_storage_adapter.cache_clear()

