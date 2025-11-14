"""Filesystem storage backend implementation."""

import shutil
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from src.storage.adapter import StorageAdapter, StorageError


class FilesystemStorage(StorageAdapter):
    """Filesystem-based storage implementation."""

    def __init__(self, base_path: str = "./storage"):
        self.base_path = Path(base_path).resolve()
        self._ensure_structure()

    def _ensure_structure(self) -> None:
        directories = [
            self.base_path / "incoming",
            self.base_path / "media" / "clusters",
            self.base_path / "media" / "derived",
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def _uri_to_path(self, uri: str) -> Path:
        """Convert a URI to a filesystem path."""
        if not uri.startswith("fs://"):
            raise StorageError(f"Invalid URI scheme: {uri}")

        # Remove 'fs://' prefix
        relative_path = uri[5:]
        return self.base_path / relative_path

    def _path_to_uri(self, path: Path) -> str:
        relative_path = path.relative_to(self.base_path)
        return f"fs://{relative_path.as_posix()}"

    def store_raw(self, request_id: str, part_id: str, file: BinaryIO, filename: str) -> str:
        try:
            # Create directory structure
            target_dir = self.base_path / "incoming" / request_id / part_id
            target_dir.mkdir(parents=True, exist_ok=True)

            # Store file
            target_path = target_dir / filename
            with open(target_path, 'wb') as f:
                shutil.copyfileobj(file, f)

            return self._path_to_uri(target_path)
        except Exception as e:
            raise StorageError(f"Failed to store raw file: {e}") from e

    def store_media(self, cluster_id: UUID, asset_id: UUID, file: BinaryIO, filename: str) -> str:
        try:
            # Create directory structure: media/clusters/{cluster_id}/
            target_dir = self.base_path / "media" / \
                "clusters" / str(cluster_id)
            target_dir.mkdir(parents=True, exist_ok=True)

            # Store file: media/clusters/{cluster_id}/{asset_id}.ext
            target_path = target_dir / filename
            with open(target_path, 'wb') as f:
                shutil.copyfileobj(file, f)

            return self._path_to_uri(target_path)
        except Exception as e:
            raise StorageError(f"Failed to store media file: {e}") from e

    def store_derived(self, cluster_id: UUID, asset_id: UUID, file: BinaryIO, filename: str) -> str:
        """Store a derived file (thumbnail, etc.)."""
        try:
            # Create directory structure
            target_dir = self.base_path / "media" / \
                "derived" / str(cluster_id) / str(asset_id)
            target_dir.mkdir(parents=True, exist_ok=True)

            # Store file
            target_path = target_dir / filename
            with open(target_path, 'wb') as f:
                shutil.copyfileobj(file, f)

            return self._path_to_uri(target_path)
        except Exception as e:
            raise StorageError(f"Failed to store derived file: {e}") from e

    def retrieve(self, uri: str) -> BinaryIO:
        """Retrieve a file by its URI."""
        try:
            path = self._uri_to_path(uri)
            if not path.exists():
                raise StorageError(f"File not found: {uri}")

            # Read file into BytesIO for consistent interface
            with open(path, 'rb') as f:
                data = f.read()
            return BytesIO(data)
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to retrieve file: {e}") from e

    def exists(self, uri: str) -> bool:
        """Check if a file exists."""
        path = self._uri_to_path(uri)
        return path.exists() and path.is_file()

    def delete(self, uri: str) -> None:
        """Delete a file."""
        try:
            path = self._uri_to_path(uri)
            if not path.exists():
                raise StorageError(f"File not found: {uri}")

            path.unlink()

            # Clean up empty parent directories (but not the incoming/, media/ root dirs)
            parent = path.parent
            base_subdirs = {
                self.base_path / "incoming",
                self.base_path / "media" / "clusters",
                self.base_path / "media" / "derived",
                self.base_path / "media"
            }
            while parent not in base_subdirs and parent != self.base_path:
                try:
                    # Check if directory is empty before removing
                    if not any(parent.iterdir()):
                        parent.rmdir()
                        parent = parent.parent
                    else:
                        break
                except OSError:
                    # Directory not empty or already removed
                    break
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to delete file: {e}") from e

    def get_size(self, uri: str) -> int:
        """Get file size in bytes."""
        try:
            path = self._uri_to_path(uri)
            if not path.exists():
                raise StorageError(f"File not found: {uri}")

            return path.stat().st_size
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to get file size: {e}") from e

    def list_files(self, prefix: str = "") -> list[str]:
        """
        List all files matching a prefix.

        Args:
            prefix: URI prefix to filter by (e.g., 'fs://incoming/')

        Returns:
            List of URI strings
        """
        try:
            if prefix:
                # Validate URI scheme if provided
                if "://" in prefix and not prefix.startswith("fs://"):
                    raise StorageError(f"Invalid URI scheme: {prefix}")

                if prefix.startswith("fs://"):
                    prefix_path = self._uri_to_path(prefix)
                else:
                    prefix_path = self.base_path / prefix
            else:
                prefix_path = self.base_path

            if not prefix_path.exists():
                return []

            files = []
            for path in prefix_path.rglob("*"):
                if path.is_file():
                    files.append(self._path_to_uri(path))

            return files
        except Exception as e:
            raise StorageError(f"Failed to list files: {e}") from e
