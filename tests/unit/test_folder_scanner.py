"""
Tests for the FolderScanner utility.
"""

from pathlib import Path
import importlib.util

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INGEST_SRC = PROJECT_ROOT / "src" / "ingest"

spec = importlib.util.spec_from_file_location(
    "folder_scanner_module", INGEST_SRC / "folder_scanner.py"
)
folder_scanner_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(folder_scanner_module)  # type: ignore[union-attr]
FolderScanner = folder_scanner_module.FolderScanner


def _create_sample_tree(root: Path):
    """Create a directory tree with mixed file types."""
    (root / ".allocatorignore").write_text(
        "\n".join(
            [
                "# Ignore comments",
                ".git",
                "cache",
                "*.tmp",
                "*.dng",
            ]
        ),
        encoding="utf-8",
    )

    # Supported files
    photos = root / "photos"
    photos.mkdir()
    (photos / "summer.jpg").write_bytes(b"fake-jpeg")
    (photos / "winter.png").write_bytes(b"fake-png")

    docs = root / "docs"
    docs.mkdir()
    (docs / "report.pdf").write_bytes(b"fake-pdf")
    (docs / "notes.txt").write_text("notes", encoding="utf-8")

    # Ignored directories and files
    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")

    cache_dir = root / "cache"
    cache_dir.mkdir()
    (cache_dir / "tmp.tmp").write_text("cache", encoding="utf-8")

    (root / "raw_data.dng").write_bytes(b"rawdata")


def test_scan_folder_respects_ignore_patterns(tmp_path):
    """Scan should exclude files and folders defined in .allocatorignore."""
    _create_sample_tree(tmp_path)
    scanner = FolderScanner()

    files = list(scanner.scan_folder(str(tmp_path)))
    names = {Path(entry["relative_path"]).as_posix() for entry in files}

    assert "photos/summer.jpg" in names
    assert "photos/winter.png" in names
    assert "docs/report.pdf" in names
    assert "docs/notes.txt" in names

    # Ignored entries should be absent.
    assert ".git/HEAD" not in names
    assert "cache/tmp.tmp" not in names
    assert "raw_data.dng" not in names


def test_scan_folder_raises_for_missing_path():
    """Non-existent folder should raise a ValueError."""
    scanner = FolderScanner()

    with pytest.raises(ValueError):
        list(scanner.scan_folder("/path/does/not/exist"))


def test_scan_folder_with_stats(tmp_path):
    """scan_folder_with_stats should aggregate counts and sizes."""
    _create_sample_tree(tmp_path)
    scanner = FolderScanner()

    files, stats = scanner.scan_folder_with_stats(str(tmp_path))

    assert stats["total_files"] == len(files) == 4
    assert stats["by_type"]["image"] == 2
    assert stats["by_type"]["document"] == 2
    assert stats["total_size_bytes"] == sum(entry["size_bytes"] for entry in files)


def test_scan_folder_unsupported_extension(tmp_path):
    """Unsupported file types should be skipped silently."""
    tmp_path.mkdir(exist_ok=True)
    scanner = FolderScanner()
    (tmp_path / ".allocatorignore").write_text("", encoding="utf-8")
    (tmp_path / "random.xyz").write_text("content", encoding="utf-8")

    files = list(scanner.scan_folder(str(tmp_path)))

    assert files == []

