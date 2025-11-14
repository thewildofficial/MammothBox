"""Abstract base class for storage backends."""

from abc import ABC, abstractmethod
from typing import BinaryIO
from uuid import UUID


class StorageError(Exception):
    pass


class StorageAdapter(ABC):

    @abstractmethod
    def store_raw(self, request_id: str, part_id: str, file: BinaryIO, filename: str) -> str:
        """Store a raw uploaded file."""
        pass

    @abstractmethod
    def store_media(self, cluster_id: UUID, asset_id: UUID, file: BinaryIO, filename: str) -> str:
        """Store a processed media file in its cluster."""
        pass

    @abstractmethod
    def store_derived(self, cluster_id: UUID, asset_id: UUID, file: BinaryIO, filename: str) -> str:
        """Store a derived file (thumbnail, etc.)."""
        pass

    @abstractmethod
    def retrieve(self, uri: str) -> BinaryIO:
        pass

    @abstractmethod
    def exists(self, uri: str) -> bool:
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
