"""
Request validator for ingestion endpoint.

Validates incoming requests (files, JSON payloads) and provides
structured validation results for the orchestrator.
"""

import json
import hashlib
from typing import List, Optional, Dict, Any, BinaryIO
from dataclasses import dataclass
from enum import Enum

from fastapi import UploadFile, HTTPException


# File size limits (in bytes)
MAX_IMAGE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_VIDEO_SIZE = 500 * 1024 * 1024  # 500MB
MAX_AUDIO_SIZE = 100 * 1024 * 1024  # 100MB
MAX_JSON_SIZE = 10 * 1024 * 1024  # 10MB
MAX_DOCUMENT_SIZE = 100 * 1024 * 1024  # 100MB (for PDFs, EPUBs, etc.)


class AssetKind(str, Enum):
    """Asset kind enumeration."""
    MEDIA = "media"
    JSON = "json"
    DOCUMENT = "document"  # For future: PDFs, EPUBs, etc.
    UNKNOWN = "unknown"


@dataclass
class ValidationResult:
    """Result of validation operation."""
    valid: bool
    kind: AssetKind
    content_type: Optional[str] = None
    size_bytes: int = 0
    error: Optional[str] = None
    error_type: Optional[str] = None  # e.g., "size_limit", "format_error", etc.
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class FileValidationResult(ValidationResult):
    """Validation result for a file upload."""
    filename: str = ""
    sha256: Optional[str] = None


@dataclass
class JsonValidationResult(ValidationResult):
    """Validation result for JSON payload."""
    parsed_data: Optional[Any] = None
    is_batch: bool = False


class IngestValidator:
    """
    Validator for ingestion requests.
    
    Handles validation of files and JSON payloads with proper
    error handling and MIME type detection.
    """
    
    # MIME type mappings
    IMAGE_TYPES = {
        "image/jpeg", "image/jpg", "image/png", "image/gif",
        "image/webp", "image/bmp", "image/tiff", "image/svg+xml"
    }
    VIDEO_TYPES = {
        "video/mp4", "video/mpeg", "video/quicktime", "video/x-msvideo",
        "video/webm", "video/x-matroska", "video/avi"
    }
    AUDIO_TYPES = {
        "audio/mpeg", "audio/mp3", "audio/wav", "audio/ogg",
        "audio/flac", "audio/aac", "audio/webm"
    }
    JSON_TYPES = {"application/json", "text/json"}
    DOCUMENT_TYPES = {
        "application/pdf",
        "application/epub+zip",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/plain",
        "text/markdown",
        "text/html",
    }
    
    def __init__(self):
        """Initialize validator."""
        pass
    
    def validate_file(self, file: UploadFile) -> FileValidationResult:
        """
        Validate an uploaded file.
        
        Args:
            file: FastAPI UploadFile object
            
        Returns:
            FileValidationResult with validation status
            
        Raises:
            HTTPException: If validation fails
        """
        try:
            # Read file content (we need to read it to compute hash and size)
            content = file.file.read()
            file.file.seek(0)  # Reset file pointer
            
            size_bytes = len(content)
            
            # Detect content type
            content_type = file.content_type or self._detect_content_type(content, file.filename)
            
            # Determine asset kind
            kind = self._determine_kind(content_type)
            
            # Validate size based on kind and content type
            max_size = self._get_max_size_for_kind(kind, content_type)
            if size_bytes > max_size:
                return FileValidationResult(
                    valid=False,
                    kind=kind,
                    content_type=content_type,
                    size_bytes=size_bytes,
                    error=f"File size {size_bytes} exceeds maximum {max_size} bytes for {kind.value}",
                    error_type="size_limit"
                )
            
            # Compute SHA256 hash
            sha256 = hashlib.sha256(content).hexdigest()
            
            return FileValidationResult(
                valid=True,
                kind=kind,
                content_type=content_type,
                size_bytes=size_bytes,
                filename=file.filename or "unknown",
                sha256=sha256,
                metadata={"original_filename": file.filename}
            )
            
        except Exception as e:
            return FileValidationResult(
                valid=False,
                kind=AssetKind.UNKNOWN,
                error=f"File validation error: {str(e)}"
            )
    
    def validate_json_payload(self, payload: str) -> JsonValidationResult:
        """
        Validate a JSON payload string.
        
        Args:
            payload: JSON string to validate
            
        Returns:
            JsonValidationResult with validation status
            
        Raises:
            HTTPException: If validation fails
        """
        try:
            size_bytes = len(payload.encode('utf-8'))
            
            # Check size limit
            if size_bytes > MAX_JSON_SIZE:
                return JsonValidationResult(
                    valid=False,
                    kind=AssetKind.JSON,
                    size_bytes=size_bytes,
                    error=f"JSON payload size {size_bytes} exceeds maximum {MAX_JSON_SIZE} bytes",
                    error_type="size_limit"
                )
            
            # Parse JSON
            try:
                parsed_data = json.loads(payload)
            except json.JSONDecodeError as e:
                return JsonValidationResult(
                    valid=False,
                    kind=AssetKind.JSON,
                    size_bytes=size_bytes,
                    error=f"Invalid JSON format: {str(e)}"
                )
            
            # Validate structure (must be object or array)
            if not isinstance(parsed_data, (dict, list)):
                return JsonValidationResult(
                    valid=False,
                    kind=AssetKind.JSON,
                    size_bytes=size_bytes,
                    parsed_data=parsed_data,
                    error="JSON payload must be an object or array, not a primitive"
                )
            
            # Check if it's a batch (array)
            is_batch = isinstance(parsed_data, list)
            
            # Validate batch is not empty
            if is_batch and len(parsed_data) == 0:
                return JsonValidationResult(
                    valid=False,
                    kind=AssetKind.JSON,
                    size_bytes=size_bytes,
                    parsed_data=parsed_data,
                    is_batch=True,
                    error="JSON array cannot be empty"
                )
            
            return JsonValidationResult(
                valid=True,
                kind=AssetKind.JSON,
                content_type="application/json",
                size_bytes=size_bytes,
                parsed_data=parsed_data,
                is_batch=is_batch
            )
            
        except Exception as e:
            return JsonValidationResult(
                valid=False,
                kind=AssetKind.JSON,
                error=f"JSON validation error: {str(e)}"
            )
    
    def validate_request(
        self,
        files: Optional[List[UploadFile]] = None,
        payload: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate an ingestion request.
        
        Args:
            files: Optional list of uploaded files
            payload: Optional JSON payload string
            
        Returns:
            Dictionary with validation results:
            - files: List of FileValidationResult
            - json: Optional JsonValidationResult
            - valid: Overall validation status
            
        Raises:
            HTTPException: If request is invalid
        """
        # At least one of files or payload must be provided
        if not files and not payload:
            raise HTTPException(
                status_code=400,
                detail="Either 'files[]' or 'payload' must be provided"
            )
        
        results = {
            "files": [],
            "json": None,
            "valid": True,
            "errors": []
        }
        
        # Validate files
        if files:
            for file in files:
                file_result = self.validate_file(file)
                results["files"].append(file_result)
                if not file_result.valid:
                    results["valid"] = False
                    error_info = {
                        "message": f"File {file.filename}: {file_result.error}",
                        "error_type": file_result.error_type,
                        "size_bytes": file_result.size_bytes,
                        "max_size": self._get_max_size_for_kind(file_result.kind, file_result.content_type) if file_result.error_type == "size_limit" else None
                    }
                    results["errors"].append(error_info)
        
        # Validate JSON payload
        if payload:
            json_result = self.validate_json_payload(payload)
            results["json"] = json_result
            if not json_result.valid:
                results["valid"] = False
                error_info = {
                    "message": f"JSON payload: {json_result.error}",
                    "error_type": json_result.error_type,
                    "size_bytes": json_result.size_bytes,
                    "max_size": MAX_JSON_SIZE if json_result.error_type == "size_limit" else None
                }
                results["errors"].append(error_info)
        
        return results
    
    def _detect_content_type(self, content: bytes, filename: Optional[str] = None) -> str:
        """
        Detect MIME type from content and filename.
        
        Args:
            content: File content bytes
            filename: Optional filename for extension-based detection
            
        Returns:
            MIME type string
        """
        # Try python-magic or filetype if available, otherwise use filename extension
        try:
            import magic
            mime = magic.from_buffer(content, mime=True)
            if mime:
                return mime
        except ImportError:
            pass
        
        # Fallback to filename extension
        if filename:
            ext = filename.lower().split('.')[-1] if '.' in filename else ''
            ext_to_mime = {
                'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
                'gif': 'image/gif', 'webp': 'image/webp', 'bmp': 'image/bmp',
                'mp4': 'video/mp4', 'avi': 'video/x-msvideo', 'mov': 'video/quicktime',
                'mp3': 'audio/mpeg', 'wav': 'audio/wav', 'ogg': 'audio/ogg',
                'pdf': 'application/pdf', 'epub': 'application/epub+zip',
                'doc': 'application/msword', 'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'txt': 'text/plain', 'md': 'text/markdown', 'html': 'text/html',
                'json': 'application/json'
            }
            return ext_to_mime.get(ext, 'application/octet-stream')
        
        return 'application/octet-stream'
    
    def _determine_kind(self, content_type: str) -> AssetKind:
        """
        Determine asset kind from content type.
        
        Args:
            content_type: MIME type string
            
        Returns:
            AssetKind enum value
        """
        if content_type in self.IMAGE_TYPES | self.VIDEO_TYPES | self.AUDIO_TYPES:
            return AssetKind.MEDIA
        elif content_type in self.JSON_TYPES:
            return AssetKind.JSON
        elif content_type in self.DOCUMENT_TYPES:
            return AssetKind.DOCUMENT
        else:
            return AssetKind.UNKNOWN
    
    def _get_max_size_for_kind(self, kind: AssetKind, content_type: Optional[str] = None) -> int:
        """
        Get maximum file size for asset kind.
        
        Args:
            kind: AssetKind enum value
            content_type: Optional MIME type for finer-grained limits
            
        Returns:
            Maximum size in bytes
        """
        if kind == AssetKind.MEDIA:
            if content_type and content_type in self.IMAGE_TYPES:
                return MAX_IMAGE_SIZE
            elif content_type and content_type in self.VIDEO_TYPES:
                return MAX_VIDEO_SIZE
            elif content_type and content_type in self.AUDIO_TYPES:
                return MAX_AUDIO_SIZE
            else:
                return MAX_VIDEO_SIZE  # Default to largest for unknown media
        elif kind == AssetKind.JSON:
            return MAX_JSON_SIZE
        elif kind == AssetKind.DOCUMENT:
            return MAX_DOCUMENT_SIZE
        else:
            return MAX_DOCUMENT_SIZE  # Default fallback

