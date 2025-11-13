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
    Processes assets that were pre-created by the orchestrator.
    """
    
    def process(self, job_data: dict, db: Session) -> Dict[str, Any]:
        """
        Process a JSON job.
        
        Args:
            job_data: Job payload containing:
                - job_id: Job UUID string
                - json_payload: JSON documents (list or dict)
                - request_id: Request identifier
                - owner: Optional owner
                - comments: Optional comments (used as collection_name_hint)
            db: Database session
            
        Returns:
            Dictionary with processing results
        """
        try:
            from src.catalog.models import Job, Asset
            
            job_id_str = job_data.get("job_id")
            if not job_id_str:
                raise ValueError("No job_id provided in job data")
            
            job_id = UUID(job_id_str)
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                raise ValueError(f"Job {job_id} not found")
            
            # Get existing assets (created by orchestrator)
            asset_ids = job.asset_ids or []
            if not asset_ids:
                raise ValueError(f"No assets found for job {job_id}")
            
            # Get JSON payload
            json_payload = job_data.get("json_payload")
            if not json_payload:
                raise ValueError("No json_payload provided in job data")
            
            # Normalize to list
            if isinstance(json_payload, dict):
                documents = [json_payload]
            else:
                documents = json_payload
            
            if len(documents) != len(asset_ids):
                logger.warning(
                    f"Document count ({len(documents)}) doesn't match asset count ({len(asset_ids)})"
                )
            
            request_id = job_data.get("request_id")
            owner = job_data.get("owner")
            collection_name_hint = job_data.get("comments")  # Use comments as hint
            
            # Create processor and process documents
            processor = JsonProcessor(db)
            result = processor.process_documents(
                documents=documents,
                request_id=request_id,
                owner=owner,
                collection_name_hint=collection_name_hint
            )
            
            # Update existing assets with schema_id and status
            assets = db.query(Asset).filter(Asset.id.in_(asset_ids)).all()
            for i, asset in enumerate(assets):
                if i < len(result["asset_ids"]):
                    # Update asset with schema and final status
                    asset.schema_id = result["schema_id"]
                    # Status will be set based on schema status in processor
                    if result.get("status") == "active":
                        asset.status = "done"
                    else:
                        asset.status = "queued"  # Waiting for schema approval
            
            db.commit()
            
            logger.info(
                f"Processed {len(documents)} JSON documents for request {request_id}. "
                f"Storage: {result['storage_choice']}"
            )
            
            return {
                "success": True,
                "asset_ids": [str(aid) for aid in asset_ids],
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
    For now, just marks assets as processing and logs lineage.
    """
    
    def process(self, job_data: dict, db: Session) -> Dict[str, Any]:
        """
        Process a media job.
        
        Args:
            job_data: Job payload containing:
                - job_id: Job UUID string
                - request_id: Request identifier
                - files: List of file metadata
            db: Database session
            
        Returns:
            Dictionary with processing results
        """
        try:
            from src.catalog.models import Job, Asset, Lineage
            from uuid import uuid4
            
            job_id_str = job_data.get("job_id")
            if not job_id_str:
                raise ValueError("No job_id provided in job data")
            
            job_id = UUID(job_id_str)
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                raise ValueError(f"Job {job_id} not found")
            
            # Get existing assets (created by orchestrator)
            asset_ids = job.asset_ids or []
            if not asset_ids:
                raise ValueError(f"No assets found for job {job_id}")
            
            request_id = job_data.get("request_id")
            
            # Update assets to processing status
            assets = db.query(Asset).filter(Asset.id.in_(asset_ids)).all()
            for asset in assets:
                asset.status = "processing"
            
            # Log lineage
            for asset in assets:
                lineage = Lineage(
                    id=uuid4(),
                    request_id=request_id,
                    asset_id=asset.id,
                    stage="media_processing_started",
                    detail={
                        "content_type": asset.content_type,
                        "size_bytes": asset.size_bytes
                    },
                    success=True
                )
                db.add(lineage)
            
            db.commit()
            
            logger.info(
                f"Media processing started for {len(assets)} assets in request {request_id}"
            )
            
            # For now, return success but note that processing is not complete
            return {
                "success": True,
                "asset_ids": [str(aid) for aid in asset_ids],
                "message": "Media processing pipeline not yet implemented. Assets marked as processing."
            }
            
        except Exception as e:
            logger.error(f"Unexpected error processing media job: {e}", exc_info=True)
            raise

