"""
Storage factory for creating storage adapter instances.

Provides singleton access to storage backends based on configuration.
"""

from functools import lru_cache
from typing import Optional

from src.config.settings import get_settings
from src.storage.adapter import StorageAdapter
from src.storage.filesystem import FilesystemStorage
from src.storage.s3 import S3Storage


_storage_instance: Optional[StorageAdapter] = None


@lru_cache()
def get_storage_adapter() -> StorageAdapter:
    """
    Get or create the storage adapter instance.
    
    Returns:
        StorageAdapter instance (FilesystemStorage or S3Storage)
    """
    global _storage_instance
    
    if _storage_instance is None:
        settings = get_settings()
        
        if settings.storage_backend.startswith("s3://"):
            _storage_instance = S3Storage(
                bucket=settings.s3_bucket,
                access_key_id=settings.aws_access_key_id,
                secret_access_key=settings.aws_secret_access_key,
                region=settings.aws_region
            )
        else:
            # Default to filesystem
            _storage_instance = FilesystemStorage(base_path=settings.storage_path)
    
    return _storage_instance


def reset_storage_adapter() -> None:
    """Reset the storage adapter instance (useful for testing)."""
    global _storage_instance
    _storage_instance = None
    get_storage_adapter.cache_clear()

