"""
Storage manager for creating and managing storage adapter instances.

Provides a factory function to create the appropriate storage backend
based on configuration settings.
"""

from functools import lru_cache
from typing import Optional

from src.config.settings import get_settings
from src.storage.adapter import StorageAdapter
from src.storage.filesystem import FilesystemStorage
from src.storage.s3 import S3Storage


@lru_cache()
def get_storage_adapter() -> StorageAdapter:
    """
    Get the configured storage adapter instance.
    
    Returns:
        StorageAdapter instance (FilesystemStorage or S3Storage)
        
    Raises:
        ValueError: If storage backend is not supported
    """
    settings = get_settings()
    
    if settings.storage_backend == "fs://" or settings.storage_backend == "filesystem":
        return FilesystemStorage(base_path=settings.storage_path)
    elif settings.storage_backend == "s3://" or settings.storage_backend == "s3":
        return S3Storage(
            bucket=settings.s3_bucket,
            access_key_id=settings.aws_access_key_id,
            secret_access_key=settings.aws_secret_access_key,
            region=settings.aws_region
        )
    else:
        raise ValueError(
            f"Unsupported storage backend: {settings.storage_backend}. "
            "Supported backends: 'fs://', 'filesystem', 's3://', 's3'"
        )


def reset_storage_adapter() -> None:
    """Reset the cached storage adapter (useful for testing)."""
    get_storage_adapter.cache_clear()

