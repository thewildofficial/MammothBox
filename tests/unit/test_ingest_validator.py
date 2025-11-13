"""
Unit tests for ingestion validator.
"""

import pytest
from io import BytesIO
from fastapi import UploadFile

from src.ingest.validator import (
    IngestValidator,
    AssetKind,
    MAX_IMAGE_SIZE,
    MAX_VIDEO_SIZE,
    MAX_JSON_SIZE,
)


class TestIngestValidator:
    """Tests for IngestValidator."""
    
    @pytest.fixture
    def validator(self):
        """Create validator instance."""
        return IngestValidator()
    
    def test_validate_json_object(self, validator):
        """Test validation of JSON object."""
        payload = '{"name": "John", "age": 30}'
        result = validator.validate_json_payload(payload)
        
        assert result.valid is True
        assert result.kind == AssetKind.JSON
        assert result.parsed_data == {"name": "John", "age": 30}
        assert result.is_batch is False
    
    def test_validate_json_array(self, validator):
        """Test validation of JSON array."""
        payload = '[{"name": "John"}, {"name": "Jane"}]'
        result = validator.validate_json_payload(payload)
        
        assert result.valid is True
        assert result.kind == AssetKind.JSON
        assert len(result.parsed_data) == 2
        assert result.is_batch is True
    
    def test_validate_json_invalid(self, validator):
        """Test validation of invalid JSON."""
        payload = '{"name": "John"'  # Missing closing brace
        result = validator.validate_json_payload(payload)
        
        assert result.valid is False
        assert result.error is not None
    
    def test_validate_json_primitive(self, validator):
        """Test validation rejects primitives."""
        payload = '"just a string"'
        result = validator.validate_json_payload(payload)
        
        assert result.valid is False
        assert "object or array" in result.error.lower()
    
    def test_validate_json_empty_array(self, validator):
        """Test validation rejects empty array."""
        payload = '[]'
        result = validator.validate_json_payload(payload)
        
        assert result.valid is False
        assert "empty" in result.error.lower()
    
    def test_validate_json_too_large(self, validator):
        """Test validation rejects oversized JSON."""
        # Create a payload larger than MAX_JSON_SIZE
        large_payload = '{"data": "' + 'x' * (MAX_JSON_SIZE + 1) + '"}'
        result = validator.validate_json_payload(large_payload)
        
        assert result.valid is False
        assert "exceeds maximum" in result.error.lower()
    
    def test_validate_file_image(self, validator):
        """Test validation of image file."""
        # Create a simple JPEG file (minimal valid JPEG)
        jpeg_data = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xd9'
        # Use mock to set content_type
        from unittest.mock import Mock
        file = Mock(spec=UploadFile)
        file.filename = "test.jpg"
        file.file = BytesIO(jpeg_data)
        file.content_type = "image/jpeg"
        
        result = validator.validate_file(file)
        
        assert result.valid is True
        assert result.kind == AssetKind.MEDIA
        assert result.content_type == "image/jpeg"
        assert result.sha256 is not None
    
    def test_validate_file_too_large(self, validator):
        """Test validation rejects oversized file."""
        # Create file larger than MAX_VIDEO_SIZE
        large_data = b'x' * (MAX_VIDEO_SIZE + 1)
        from unittest.mock import Mock
        file = Mock(spec=UploadFile)
        file.filename = "large.mp4"
        file.file = BytesIO(large_data)
        file.content_type = "video/mp4"
        
        result = validator.validate_file(file)
        
        assert result.valid is False
        assert "exceeds maximum" in result.error.lower()
    
    def test_validate_request_files_only(self, validator):
        """Test validation of request with files only."""
        jpeg_data = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xd9'
        from unittest.mock import Mock
        file = Mock(spec=UploadFile)
        file.filename = "test.jpg"
        file.file = BytesIO(jpeg_data)
        file.content_type = "image/jpeg"
        
        results = validator.validate_request(files=[file])
        
        assert results["valid"] is True
        assert len(results["files"]) == 1
        assert results["json"] is None
    
    def test_validate_request_json_only(self, validator):
        """Test validation of request with JSON only."""
        payload = '{"name": "John"}'
        
        results = validator.validate_request(payload=payload)
        
        assert results["valid"] is True
        assert len(results["files"]) == 0
        assert results["json"] is not None
        assert results["json"].valid is True
    
    def test_validate_request_mixed(self, validator):
        """Test validation of request with both files and JSON."""
        jpeg_data = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xd9'
        from unittest.mock import Mock
        file = Mock(spec=UploadFile)
        file.filename = "test.jpg"
        file.file = BytesIO(jpeg_data)
        file.content_type = "image/jpeg"
        payload = '{"description": "Test image"}'
        
        results = validator.validate_request(files=[file], payload=payload)
        
        assert results["valid"] is True
        assert len(results["files"]) == 1
        assert results["json"] is not None
    
    def test_validate_request_empty(self, validator):
        """Test validation rejects empty request."""
        with pytest.raises(Exception):  # Should raise HTTPException
            validator.validate_request()

