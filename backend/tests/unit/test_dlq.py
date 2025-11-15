"""
Unit tests for Dead Letter Queue (DLQ).
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from src.queue.dlq import DeadLetterQueue, get_dlq


class TestDeadLetterQueue:
    """Tests for DeadLetterQueue class."""

    @pytest.fixture
    def temp_dlq_path(self):
        """Create temporary directory for DLQ."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def dlq(self, temp_dlq_path):
        """Create DLQ instance with temp path."""
        return DeadLetterQueue(storage_path=temp_dlq_path)

    def test_dlq_initialization(self, dlq, temp_dlq_path):
        """DLQ should initialize and create storage directory."""
        assert dlq.storage_path == Path(temp_dlq_path)
        assert dlq.storage_path.exists()
        assert dlq.storage_path.is_dir()

    def test_add_failed_job(self, dlq):
        """Should add failed job to DLQ."""
        job_data = {"request_id": "test_123", "data": "sample"}

        dlq.add(
            job_id="job_001",
            job_type="json",
            job_data=job_data,
            error="Test error message",
            retries=3
        )

        # Check file was created
        files = list(dlq.storage_path.glob("json_job_001_*.json"))
        assert len(files) == 1

        # Verify content
        with open(files[0], 'r') as f:
            entry = json.load(f)

        assert entry["job_id"] == "job_001"
        assert entry["job_type"] == "json"
        assert entry["job_data"] == job_data
        assert entry["error"] == "Test error message"
        assert entry["retries"] == 3
        assert "dlq_timestamp" in entry

    def test_list_all_jobs(self, dlq):
        """Should list all jobs in DLQ."""
        # Add multiple jobs
        for i in range(3):
            dlq.add(
                job_id=f"job_{i:03d}",
                job_type="media" if i % 2 == 0 else "json",
                job_data={"id": i},
                error=f"Error {i}",
                retries=i + 1
            )

        # List all
        jobs = dlq.list()
        assert len(jobs) == 3

        # Check they have dlq_file field
        for job in jobs:
            assert "dlq_file" in job
            assert "job_id" in job

    def test_list_filtered_by_type(self, dlq):
        """Should filter jobs by type."""
        # Add mixed types
        dlq.add("job_1", "json", {}, "Error", 1)
        dlq.add("job_2", "media", {}, "Error", 1)
        dlq.add("job_3", "json", {}, "Error", 1)

        # Filter by json
        json_jobs = dlq.list(job_type="json")
        assert len(json_jobs) == 2
        assert all(job["job_type"] == "json" for job in json_jobs)

        # Filter by media
        media_jobs = dlq.list(job_type="media")
        assert len(media_jobs) == 1
        assert media_jobs[0]["job_type"] == "media"

    def test_list_with_limit(self, dlq):
        """Should respect limit parameter."""
        # Add 10 jobs
        for i in range(10):
            dlq.add(f"job_{i:03d}", "json", {}, "Error", 1)

        # List with limit
        jobs = dlq.list(limit=5)
        assert len(jobs) == 5

    def test_get_specific_job(self, dlq):
        """Should retrieve specific job by ID."""
        job_data = {"test": "data"}
        dlq.add("job_xyz", "json", job_data, "Test error", 2)

        # Get job
        job = dlq.get("job_xyz")
        assert job is not None
        assert job["job_id"] == "job_xyz"
        assert job["job_data"] == job_data
        assert job["error"] == "Test error"

    def test_get_nonexistent_job(self, dlq):
        """Should return None for nonexistent job."""
        job = dlq.get("nonexistent")
        assert job is None

    def test_remove_job(self, dlq):
        """Should remove job from DLQ."""
        dlq.add("job_remove", "json", {}, "Error", 1)

        # Verify exists
        assert dlq.get("job_remove") is not None

        # Remove
        result = dlq.remove("job_remove")
        assert result is True

        # Verify removed
        assert dlq.get("job_remove") is None

    def test_remove_nonexistent_job(self, dlq):
        """Should return False when removing nonexistent job."""
        result = dlq.remove("nonexistent")
        assert result is False

    def test_count_all(self, dlq):
        """Should count all jobs."""
        dlq.add("job_1", "json", {}, "Error", 1)
        dlq.add("job_2", "media", {}, "Error", 1)
        dlq.add("job_3", "json", {}, "Error", 1)

        count = dlq.count()
        assert count == 3

    def test_count_by_type(self, dlq):
        """Should count jobs by type."""
        dlq.add("job_1", "json", {}, "Error", 1)
        dlq.add("job_2", "media", {}, "Error", 1)
        dlq.add("job_3", "json", {}, "Error", 1)
        dlq.add("job_4", "media", {}, "Error", 1)

        json_count = dlq.count(job_type="json")
        media_count = dlq.count(job_type="media")

        assert json_count == 2
        assert media_count == 2

    def test_get_dlq_singleton(self, temp_dlq_path):
        """get_dlq should return singleton instance."""
        # This test needs to be careful with global state
        # Just verify it returns a DLQ instance
        dlq = get_dlq()
        assert isinstance(dlq, DeadLetterQueue)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
