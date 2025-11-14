"""
Recursive folder scanner for bulk ingestion.

Scans directories recursively, respects ignore patterns, and yields
file metadata for batch ingestion workflows.
"""

import logging
import os
from pathlib import Path
from typing import Generator, Optional

logger = logging.getLogger(__name__)

# Supported file extensions by category
SUPPORTED_EXTENSIONS = {
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.tif'],
    'video': ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.m4v'],
    'document': ['.pdf', '.epub', '.docx', '.pptx', '.txt', '.md'],
    'json': ['.json']
}


class FolderScanner:
    """
    Recursively discovers files in folders with ignore pattern support.
    
    Supports .allocatorignore files (gitignore-style) for excluding paths
    from ingestion (e.g., node_modules, .git, temp files).
    """
    
    def __init__(self, ignore_file: str = '.allocatorignore'):
        """
        Initialize folder scanner.
        
        Args:
            ignore_file: Name of ignore file to look for (default: .allocatorignore)
        """
        self.ignore_file = ignore_file
        self.ignore_patterns = []
    
    def load_ignore_patterns(self, root_path: Path) -> None:
        """
        Load ignore patterns from .allocatorignore file.
        
        Supports gitignore-style patterns:
        - Lines starting with # are comments
        - Empty lines are ignored
        - Simple substring matching (not full glob support)
        
        Args:
            root_path: Root directory to search for ignore file
        """
        ignore_path = root_path / self.ignore_file
        if ignore_path.exists():
            try:
                with open(ignore_path, 'r', encoding='utf-8') as f:
                    self.ignore_patterns = [
                        line.strip() for line in f
                        if line.strip() and not line.startswith('#')
                    ]
                logger.info(
                    f"Loaded {len(self.ignore_patterns)} ignore patterns from {ignore_path}"
                )
            except Exception as e:
                logger.warning(f"Failed to load ignore patterns from {ignore_path}: {e}")
        else:
            logger.debug(f"No ignore file found at {ignore_path}")
    
    def should_ignore(self, path: Path) -> bool:
        """
        Check if path matches any ignore patterns.
        
        Uses simple substring matching for patterns. A path is ignored if
        any pattern appears in the path string.
        
        Args:
            path: Path to check
            
        Returns:
            True if path should be ignored
        """
        path_str = str(path)
        for pattern in self.ignore_patterns:
            if pattern in path_str:
                return True
        return False
    
    def get_file_type(self, path: Path) -> Optional[str]:
        """
        Determine file type from extension.
        
        Args:
            path: File path
            
        Returns:
            File type ('image', 'video', 'document', 'json') or None if unsupported
        """
        ext = path.suffix.lower()
        for file_type, extensions in SUPPORTED_EXTENSIONS.items():
            if ext in extensions:
                return file_type
        return None
    
    def scan_folder(self, folder_path: str) -> Generator[dict, None, None]:
        """
        Recursively scan folder and yield file metadata.
        
        Args:
            folder_path: Path to folder to scan
            
        Yields:
            Dictionary containing:
            - path: Absolute file path
            - relative_path: Path relative to scan root
            - type: File type category
            - size_bytes: File size in bytes
            
        Raises:
            ValueError: If folder doesn't exist or is not a directory
        """
        root = Path(folder_path).resolve()
        
        # Validation
        if not root.exists():
            raise ValueError(f"Folder not found: {folder_path}")
        
        if not root.is_dir():
            raise ValueError(f"Not a directory: {folder_path}")
        
        # Load ignore patterns from root
        self.load_ignore_patterns(root)
        
        # Walk directory tree
        file_count = 0
        ignored_count = 0
        
        for dirpath, dirnames, filenames in os.walk(root):
            current_dir = Path(dirpath)
            
            # Filter out ignored directories (in-place modification to skip traversal)
            original_dircount = len(dirnames)
            dirnames[:] = [
                d for d in dirnames
                if not self.should_ignore(current_dir / d)
            ]
            ignored_count += (original_dircount - len(dirnames))
            
            # Process files
            for filename in filenames:
                file_path = current_dir / filename
                
                # Check ignore patterns
                if self.should_ignore(file_path):
                    ignored_count += 1
                    continue
                
                # Determine file type
                file_type = self.get_file_type(file_path)
                if not file_type:
                    # Unsupported file type, skip
                    continue
                
                # Get file size
                try:
                    size_bytes = file_path.stat().st_size
                except OSError as e:
                    logger.warning(f"Failed to stat {file_path}: {e}")
                    continue
                
                file_count += 1
                
                yield {
                    'path': str(file_path),
                    'relative_path': str(file_path.relative_to(root)),
                    'type': file_type,
                    'size_bytes': size_bytes
                }
        
        logger.info(
            f"Scan complete: {file_count} files found, {ignored_count} paths ignored"
        )
    
    def scan_folder_with_stats(self, folder_path: str) -> tuple[list[dict], dict]:
        """
        Scan folder and return files with statistics.
        
        Args:
            folder_path: Path to folder to scan
            
        Returns:
            Tuple of (files list, stats dict)
            - files: List of file metadata dicts
            - stats: Statistics including counts by type and total size
        """
        files = []
        stats = {
            'total_files': 0,
            'total_size_bytes': 0,
            'by_type': {
                'image': 0,
                'video': 0,
                'document': 0,
                'json': 0
            }
        }
        
        for file_info in self.scan_folder(folder_path):
            files.append(file_info)
            stats['total_files'] += 1
            stats['total_size_bytes'] += file_info['size_bytes']
            stats['by_type'][file_info['type']] += 1
        
        return files, stats

