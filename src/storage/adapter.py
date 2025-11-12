"""
Abstract base class for storage backends.

Defines the interface that all storage implementations must follow.
"""

from abc import ABC, abstractmethod
from typing import BinaryIO
from uuid import UUID


class StorageError(Exception):
    """Exception raised for storage-related errors."""
    pass


class StorageAdapter(ABC):
    """
    Abstract base class for storage backends.

    All storage implementations (filesystem, S3, etc.) must implement
    these methods to provide a consistent interface.
    """

    @abstractmethod
    def store_raw(self, request_id: str, part_id: str, file: BinaryIO, filename: str) -> str:
        """
        Store a raw uploaded file.

        Args:
            request_id: Request identifier for grouping uploads
            part_id: Part identifier within the request
            file: File-like object to store
            filename: Original filename

        Returns:
            URI string for the stored file (e.g., 'fs://incoming/req123/part1/file.jpg')

        Raises:
            StorageError: If storage operation fails
        """
        pass

    @abstractmethod
    def store_media(self, cluster_id: UUID, asset_id: UUID, file: BinaryIO, filename: str) -> str:
        """
        Store a processed media file in its cluster.

        Args:
            cluster_id: Cluster UUID
            asset_id: Asset UUID
            file: File-like object to store
            filename: Filename to use

        Returns:
            URI string for the stored file

        Raises:
            StorageError: If storage operation fails
        """
        pass

    @abstractmethod
    def store_derived(self, cluster_id: UUID, asset_id: UUID, file: BinaryIO, filename: str) -> str:
        """
        Store a derived file (thumbnail, etc.).

        Args:
            cluster_id: Cluster UUID
            asset_id: Asset UUID
            file: File-like object to store
            filename: Filename to use (e.g., 'thumbnail.jpg')

        Returns:
            URI string for the stored file

        Raises:
            StorageError: If storage operation fails
        """
        pass

    @abstractmethod
    def retrieve(self, uri: str) -> BinaryIO:
        """
        Retrieve a file by its URI.

        Args:
            uri: URI string (e.g., 'fs://incoming/...' or 's3://bucket/...')

        Returns:
            File-like object

        Raises:
            StorageError: If file not found or retrieval fails
        """
        pass

    @abstractmethod
    def exists(self, uri: str) -> bool:
        """
        Check if a file exists.

        Args:
            uri: URI string

        Returns:
            True if file exists, False otherwise
        """
        pass

    @abstractmethod
    def delete(self, uri: str) -> None:
        """
        Delete a file.

        Args:
            uri: URI string

        Raises:
            StorageError: If deletion fails
        """
        pass

    @abstractmethod
    def get_size(self, uri: str) -> int:
        """
        Get file size in bytes.

        Args:
            uri: URI string

        Returns:
            File size in bytes

        Raises:
            StorageError: If file not found
        """
        pass
