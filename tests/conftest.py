# Test configuration

import pytest
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

@pytest.fixture
def test_settings():
    """Override settings for testing"""
    from src.config.settings import Settings
    return Settings(
        database_url="postgresql://postgres:postgres@localhost:5432/file_allocator_test",
        storage_backend="fs://",
        storage_path="./test_storage"
    )

