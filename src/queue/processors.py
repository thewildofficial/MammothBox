"""
Job processors for different job types.

Adapters that wrap existing processors (JsonProcessor, MediaProcessor)
to work with the queue system.
"""

import logging
from typing import Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session

from src.queue.supervisor import JobProcessor
from src.ingest.json_processor import JsonProcessor, JsonProcessingError

logger = logging.getLogger(__name__)


class JsonJobProcessor(JobProcessor):
    """
    JSON job processor adapter.
    
    Wraps JsonProcessor to work with queue system.
    """
    
    def process(self, job_data: dict, db: Session) -> Dict[str, Any]:
        """
        Process a JSON job.
        
        Args:
            job_data: Job payload containing:
                - documents: List of JSON documents
                - request_id: Request identifier
                - owner: Optional owner
                - collection_name_hint: Optional collection name hint
            db: Database session
            
        Returns:
            Dictionary with processing results
        """
        try:
            documents = job_data.get("documents", [])
            request_id = job_data.get("request_id")
            owner = job_data.get("owner")
            collection_name_hint = job_data.get("collection_name_hint")
            
            if not documents:
                raise ValueError("No documents provided in job data")
            if not request_id:
                raise ValueError("No request_id provided in job data")
            
            # Create processor and process documents
            processor = JsonProcessor(db)
            result = processor.process_documents(
                documents=documents,
                request_id=request_id,
                owner=owner,
                collection_name_hint=collection_name_hint
            )
            
            # Update job with asset IDs
            from src.catalog.models import Job
            from uuid import UUID
            job_id_str = job_data.get("job_id")
            if job_id_str:
                job_id = UUID(job_id_str)
                job = db.query(Job).filter(Job.id == job_id).first()
                if job:
                    job.asset_ids = result["asset_ids"]
                    db.commit()
            
            logger.info(
                f"Processed {len(documents)} JSON documents for request {request_id}. "
                f"Storage: {result['storage_choice']}"
            )
            
            return {
                "success": True,
                "asset_ids": [str(aid) for aid in result["asset_ids"]],
                "schema_id": str(result["schema_id"]),
                "storage_choice": result["storage_choice"],
            }
            
        except JsonProcessingError as e:
            logger.error(f"JSON processing error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing JSON job: {e}", exc_info=True)
            raise


class MediaJobProcessor(JobProcessor):
    """
    Media job processor adapter (placeholder).
    
    To be implemented when media processing pipeline is added.
    """
    
    def process(self, job_data: dict, db: Session) -> Dict[str, Any]:
        """
        Process a media job.
        
        Args:
            job_data: Job payload
            db: Database session
            
        Returns:
            Dictionary with processing results
        """
        raise NotImplementedError("Media processing not yet implemented")

