"""
Unit tests for filesystem storage backend.
"""

import io
from pathlib import Path
import uuid

import pytest

from src.storage.filesystem import FilesystemStorage
from src.storage.adapter import StorageError


@pytest.fixture
def temp_storage(tmp_path):
    """Create a temporary storage instance."""
    return FilesystemStorage(str(tmp_path))


@pytest.fixture
def sample_file():
    """Create a sample file-like object."""
    content = b"This is test content for storage"
    return io.BytesIO(content)


class TestFilesystemStorageInit:
    """Test storage initialization."""

    def test_init_creates_directory_structure(self, tmp_path):
        """Test that init creates the required directory structure."""
        storage = FilesystemStorage(str(tmp_path))

        assert (storage.base_path / "incoming").exists()
        assert (storage.base_path / "media" / "clusters").exists()
        assert (storage.base_path / "media" / "derived").exists()

    def test_init_with_existing_structure(self, tmp_path):
        """Test that init works with existing directory structure."""
        # Create directories first
        (tmp_path / "incoming").mkdir(parents=True)
        (tmp_path / "media" / "clusters").mkdir(parents=True)

        # Should not raise an error
        storage = FilesystemStorage(str(tmp_path))
        assert storage.base_path == tmp_path


class TestStoreRaw:
    """Test raw file storage."""

    def test_store_raw_basic(self, temp_storage, sample_file):
        """Test basic raw file storage."""
        request_id = "test-request-123"
        part_id = "part-1"
        filename = "test.txt"

        uri = temp_storage.store_raw(
            request_id, part_id, sample_file, filename)

        assert uri == f"fs://incoming/{request_id}/{part_id}/{filename}"
        assert temp_storage.exists(uri)

    def test_store_raw_creates_directories(self, temp_storage, sample_file):
        """Test that store_raw creates necessary directories."""
        request_id = "new-request"
        part_id = "new-part"
        filename = "file.bin"

        uri = temp_storage.store_raw(
            request_id, part_id, sample_file, filename)

        assert temp_storage.exists(uri)
        expected_dir = temp_storage.base_path / "incoming" / request_id / part_id
        assert expected_dir.exists()
        assert (expected_dir / filename).exists()

    def test_store_raw_with_special_characters(self, temp_storage, sample_file):
        """Test storing files with special characters in name."""
        request_id = "req-123"
        part_id = "part-1"
        filename = "test file (1).txt"

        uri = temp_storage.store_raw(
            request_id, part_id, sample_file, filename)

        assert temp_storage.exists(uri)
        # Verify content is preserved
        retrieved = temp_storage.retrieve(uri)
        sample_file.seek(0)
        assert retrieved.read() == sample_file.read()

    def test_store_raw_overwrites_existing(self, temp_storage):
        """Test that storing to same location overwrites."""
        request_id = "req-1"
        part_id = "part-1"
        filename = "test.txt"

        # Store first file
        file1 = io.BytesIO(b"First content")
        uri = temp_storage.store_raw(request_id, part_id, file1, filename)

        # Store second file (overwrite)
        file2 = io.BytesIO(b"Second content - different")
        uri2 = temp_storage.store_raw(request_id, part_id, file2, filename)

        assert uri == uri2
        retrieved = temp_storage.retrieve(uri)
        assert retrieved.read() == b"Second content - different"


class TestStoreMedia:
    """Test media file storage."""

    def test_store_media_basic(self, temp_storage, sample_file):
        """Test basic media file storage."""
        cluster_id = uuid.uuid4()
        asset_id = uuid.uuid4()
        filename = "video.mp4"

        uri = temp_storage.store_media(
            cluster_id, asset_id, sample_file, filename)

        expected_uri = f"fs://media/clusters/{cluster_id}/{asset_id}/{filename}"
        assert uri == expected_uri
        assert temp_storage.exists(uri)

    def test_store_media_creates_directories(self, temp_storage, sample_file):
        """Test that store_media creates directory structure."""
        cluster_id = uuid.uuid4()
        asset_id = uuid.uuid4()
        filename = "image.png"

        uri = temp_storage.store_media(
            cluster_id, asset_id, sample_file, filename)

        assert temp_storage.exists(uri)
        expected_dir = temp_storage.base_path / "media" / \
            "clusters" / str(cluster_id) / str(asset_id)
        assert expected_dir.exists()
        assert (expected_dir / filename).exists()


class TestStoreDerived:
    """Test derived file storage."""

    def test_store_derived_basic(self, temp_storage, sample_file):
        """Test basic derived file storage."""
        cluster_id = uuid.uuid4()
        asset_id = uuid.uuid4()
        filename = "thumbnail.jpg"

        uri = temp_storage.store_derived(
            cluster_id, asset_id, sample_file, filename)

        expected_uri = f"fs://media/derived/{cluster_id}/{asset_id}/{filename}"
        assert uri == expected_uri
        assert temp_storage.exists(uri)

    def test_store_derived_creates_directories(self, temp_storage, sample_file):
        """Test that store_derived creates directory structure."""
        cluster_id = uuid.uuid4()
        asset_id = uuid.uuid4()
        filename = "preview.jpg"

        uri = temp_storage.store_derived(
            cluster_id, asset_id, sample_file, filename)

        assert temp_storage.exists(uri)
        expected_dir = temp_storage.base_path / "media" / \
            "derived" / str(cluster_id) / str(asset_id)
        assert expected_dir.exists()
        assert (expected_dir / filename).exists()


class TestRetrieve:
    """Test file retrieval."""

    def test_retrieve_existing_file(self, temp_storage, sample_file):
        """Test retrieving an existing file."""
        request_id = "req-1"
        part_id = "part-1"
        filename = "test.bin"

        uri = temp_storage.store_raw(
            request_id, part_id, sample_file, filename)

        # Retrieve and compare
        retrieved = temp_storage.retrieve(uri)
        sample_file.seek(0)
        assert retrieved.read() == sample_file.read()

    def test_retrieve_nonexistent_file(self, temp_storage):
        """Test retrieving a file that doesn't exist."""
        uri = "fs://incoming/fake/path/nonexistent.txt"

        with pytest.raises(StorageError, match="not found"):
            temp_storage.retrieve(uri)

    def test_retrieve_invalid_uri_scheme(self, temp_storage):
        """Test retrieving with invalid URI scheme."""
        uri = "s3://bucket/key/file.txt"

        with pytest.raises(StorageError, match="Invalid URI scheme"):
            temp_storage.retrieve(uri)

    def test_retrieve_returns_bytesio(self, temp_storage, sample_file):
        """Test that retrieve returns a BytesIO object."""
        request_id = "req-1"
        part_id = "part-1"
        filename = "test.txt"

        uri = temp_storage.store_raw(
            request_id, part_id, sample_file, filename)
        retrieved = temp_storage.retrieve(uri)

        assert isinstance(retrieved, io.BytesIO)
        # Should be readable multiple times
        content1 = retrieved.read()
        retrieved.seek(0)
        content2 = retrieved.read()
        assert content1 == content2


class TestExists:
    """Test file existence checks."""

    def test_exists_true_for_stored_file(self, temp_storage, sample_file):
        """Test that exists returns True for stored files."""
        request_id = "req-1"
        part_id = "part-1"
        filename = "test.txt"

        uri = temp_storage.store_raw(
            request_id, part_id, sample_file, filename)

        assert temp_storage.exists(uri) is True

    def test_exists_false_for_nonexistent_file(self, temp_storage):
        """Test that exists returns False for nonexistent files."""
        uri = "fs://incoming/fake/path/nonexistent.txt"

        assert temp_storage.exists(uri) is False

    def test_exists_invalid_uri_scheme(self, temp_storage):
        """Test exists with invalid URI scheme."""
        uri = "http://example.com/file.txt"

        with pytest.raises(StorageError, match="Invalid URI scheme"):
            temp_storage.exists(uri)


class TestDelete:
    """Test file deletion."""

    def test_delete_existing_file(self, temp_storage, sample_file):
        """Test deleting an existing file."""
        request_id = "req-1"
        part_id = "part-1"
        filename = "test.txt"

        uri = temp_storage.store_raw(
            request_id, part_id, sample_file, filename)
        assert temp_storage.exists(uri)

        temp_storage.delete(uri)
        assert not temp_storage.exists(uri)

    def test_delete_removes_empty_directories(self, temp_storage, sample_file):
        """Test that delete removes empty parent directories."""
        request_id = "req-delete-test"
        part_id = "part-only"
        filename = "only-file.txt"

        uri = temp_storage.store_raw(
            request_id, part_id, sample_file, filename)

        # Verify directory structure exists
        part_dir = temp_storage.base_path / "incoming" / request_id / part_id
        assert part_dir.exists()

        # Delete the file
        temp_storage.delete(uri)

        # Empty directories should be removed
        assert not part_dir.exists()
        # But not the parent if it has other content
        incoming_dir = temp_storage.base_path / "incoming"
        assert incoming_dir.exists()

    def test_delete_nonexistent_file_raises_error(self, temp_storage):
        """Test that deleting nonexistent file raises error."""
        uri = "fs://incoming/fake/path/nonexistent.txt"

        with pytest.raises(StorageError, match="not found"):
            temp_storage.delete(uri)

    def test_delete_invalid_uri_scheme(self, temp_storage):
        """Test delete with invalid URI scheme."""
        uri = "ftp://server/path/file.txt"

        with pytest.raises(StorageError, match="Invalid URI scheme"):
            temp_storage.delete(uri)


class TestGetSize:
    """Test file size retrieval."""

    def test_get_size_existing_file(self, temp_storage):
        """Test getting size of existing file."""
        content = b"Test content with known size"
        file = io.BytesIO(content)

        request_id = "req-1"
        part_id = "part-1"
        filename = "sized.txt"

        uri = temp_storage.store_raw(request_id, part_id, file, filename)
        size = temp_storage.get_size(uri)

        assert size == len(content)

    def test_get_size_nonexistent_file(self, temp_storage):
        """Test getting size of nonexistent file."""
        uri = "fs://incoming/fake/path/nonexistent.txt"

        with pytest.raises(StorageError, match="not found"):
            temp_storage.get_size(uri)

    def test_get_size_zero_byte_file(self, temp_storage):
        """Test getting size of empty file."""
        file = io.BytesIO(b"")

        request_id = "req-1"
        part_id = "part-1"
        filename = "empty.txt"

        uri = temp_storage.store_raw(request_id, part_id, file, filename)
        size = temp_storage.get_size(uri)

        assert size == 0


class TestListFiles:
    """Test file listing."""

    def test_list_files_in_directory(self, temp_storage, sample_file):
        """Test listing files in a directory."""
        request_id = "req-list"
        part_id = "part-1"

        # Store multiple files
        filenames = ["file1.txt", "file2.txt", "file3.txt"]
        for filename in filenames:
            sample_file.seek(0)
            temp_storage.store_raw(request_id, part_id, sample_file, filename)

        # List files
        prefix = f"fs://incoming/{request_id}/{part_id}/"
        files = temp_storage.list_files(prefix)

        assert len(files) == 3
        assert all(f.startswith(prefix) for f in files)
        assert all(any(f.endswith(fn) for fn in filenames) for f in files)

    def test_list_files_empty_directory(self, temp_storage):
        """Test listing files in empty directory."""
        prefix = "fs://incoming/empty/dir/"
        files = temp_storage.list_files(prefix)

        assert files == []

    def test_list_files_with_subdirectories(self, temp_storage, sample_file):
        """Test listing respects subdirectories."""
        request_id = "req-multi"

        # Store files in different parts
        temp_storage.store_raw(request_id, "part-1", sample_file, "file1.txt")
        sample_file.seek(0)
        temp_storage.store_raw(request_id, "part-2", sample_file, "file2.txt")

        # List all files under request
        prefix = f"fs://incoming/{request_id}/"
        files = temp_storage.list_files(prefix)

        assert len(files) == 2
        assert any("part-1/file1.txt" in f for f in files)
        assert any("part-2/file2.txt" in f for f in files)

    def test_list_files_invalid_uri(self, temp_storage):
        """Test list_files with invalid URI."""
        prefix = "http://example.com/"

        with pytest.raises(StorageError, match="Invalid URI scheme"):
            temp_storage.list_files(prefix)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_large_file_storage(self, temp_storage):
        """Test storing a larger file."""
        # Create a 1MB file
        large_content = b"x" * (1024 * 1024)
        large_file = io.BytesIO(large_content)

        request_id = "req-large"
        part_id = "part-1"
        filename = "large.bin"

        uri = temp_storage.store_raw(request_id, part_id, large_file, filename)

        # Verify size
        assert temp_storage.get_size(uri) == len(large_content)

        # Verify retrieval
        retrieved = temp_storage.retrieve(uri)
        assert retrieved.read() == large_content

    def test_unicode_filename(self, temp_storage, sample_file):
        """Test storing files with unicode names."""
        request_id = "req-unicode"
        part_id = "part-1"
        filename = "тест_文件_📁.txt"

        uri = temp_storage.store_raw(
            request_id, part_id, sample_file, filename)

        assert temp_storage.exists(uri)
        retrieved = temp_storage.retrieve(uri)
        sample_file.seek(0)
        assert retrieved.read() == sample_file.read()

    def test_relative_path_resolution(self, temp_storage):
        """Test that relative paths are properly resolved."""
        # Create storage with relative path
        storage = FilesystemStorage("./test_storage")

        # Base path should be absolute
        assert storage.base_path.is_absolute()

        # Cleanup
        import shutil
        if Path("./test_storage").exists():
            shutil.rmtree("./test_storage")
