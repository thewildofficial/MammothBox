"""
Dead Letter Queue (DLQ) for permanently failed jobs.

Handles jobs that have exhausted all retry attempts.
Provides storage, retrieval, and monitoring of failed jobs.
"""

import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path

from src.common.metrics import dead_letter_queue_depth

logger = logging.getLogger(__name__)


class DeadLetterQueue:
    """
    Dead Letter Queue for permanently failed jobs.

    Stores failed jobs with full context for manual investigation.
    """

    def __init__(self, storage_path: str = "./storage/dlq"):
        """
        Initialize DLQ.

        Args:
            storage_path: Path to store DLQ entries
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Update metrics on initialization
        self._update_metrics()

    def add(
        self,
        job_id: str,
        job_type: str,
        job_data: Dict[str, Any],
        error: str,
        retries: int,
        original_timestamp: Optional[str] = None,
    ):
        """
        Add a failed job to DLQ.

        Args:
            job_id: Job identifier
            job_type: Job type (json/media)
            job_data: Original job data
            error: Error message/traceback
            retries: Number of retries attempted
            original_timestamp: When job was originally submitted
        """
        entry = {
            "job_id": job_id,
            "job_type": job_type,
            "job_data": job_data,
            "error": error,
            "retries": retries,
            "original_timestamp": original_timestamp or datetime.utcnow().isoformat(),
            "dlq_timestamp": datetime.utcnow().isoformat(),
        }

        # Write to file
        filename = f"{job_type}_{job_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.storage_path / filename

        try:
            with open(filepath, 'w') as f:
                json.dump(entry, f, indent=2)

            logger.error(
                f"Job {job_id} ({job_type}) moved to DLQ after {retries} retries",
                extra={
                    "extra_fields": {
                        "job_id": job_id,
                        "job_type": job_type,
                        "error": error,
                        "dlq_file": str(filepath),
                    }
                }
            )

            # Update metrics
            self._update_metrics()

        except Exception as e:
            logger.critical(f"Failed to write to DLQ: {e}")

    def list(
        self,
        job_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List jobs in DLQ.

        Args:
            job_type: Filter by job type (optional)
            limit: Maximum number of entries to return

        Returns:
            List of DLQ entries
        """
        entries = []

        for filepath in sorted(self.storage_path.glob("*.json"), reverse=True):
            if len(entries) >= limit:
                break

            # Filter by job type if specified
            if job_type and not filepath.name.startswith(f"{job_type}_"):
                continue

            try:
                with open(filepath, 'r') as f:
                    entry = json.load(f)
                    entry["dlq_file"] = filepath.name
                    entries.append(entry)
            except Exception as e:
                logger.warning(f"Failed to read DLQ entry {filepath}: {e}")

        return entries

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific job from DLQ by ID.

        Args:
            job_id: Job identifier

        Returns:
            DLQ entry or None if not found
        """
        for filepath in self.storage_path.glob(f"*_{job_id}_*.json"):
            try:
                with open(filepath, 'r') as f:
                    entry = json.load(f)
                    entry["dlq_file"] = filepath.name
                    return entry
            except Exception as e:
                logger.warning(f"Failed to read DLQ entry {filepath}: {e}")

        return None

    def remove(self, job_id: str) -> bool:
        """
        Remove a job from DLQ (after manual resolution).

        Args:
            job_id: Job identifier

        Returns:
            True if removed, False if not found
        """
        for filepath in self.storage_path.glob(f"*_{job_id}_*.json"):
            try:
                filepath.unlink()
                logger.info(f"Removed job {job_id} from DLQ")
                self._update_metrics()
                return True
            except Exception as e:
                logger.error(f"Failed to remove DLQ entry {filepath}: {e}")
                return False

        return False

    def count(self, job_type: Optional[str] = None) -> int:
        """
        Count jobs in DLQ.

        Args:
            job_type: Filter by job type (optional)

        Returns:
            Number of jobs in DLQ
        """
        if job_type:
            return len(list(self.storage_path.glob(f"{job_type}_*.json")))
        else:
            return len(list(self.storage_path.glob("*.json")))

    def _update_metrics(self):
        """Update Prometheus metrics for DLQ depth."""
        try:
            json_count = len(list(self.storage_path.glob("json_*.json")))
            media_count = len(list(self.storage_path.glob("media_*.json")))

            dead_letter_queue_depth.labels(job_type="json").set(json_count)
            dead_letter_queue_depth.labels(job_type="media").set(media_count)
        except Exception as e:
            logger.warning(f"Failed to update DLQ metrics: {e}")


# Global DLQ instance
_dlq: Optional[DeadLetterQueue] = None


def get_dlq() -> DeadLetterQueue:
    """Get global DLQ instance."""
    global _dlq
    if _dlq is None:
        _dlq = DeadLetterQueue()
    return _dlq
