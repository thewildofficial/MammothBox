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
from src.media.service import MediaService, MediaServiceError
from src.storage.factory import get_storage_adapter

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
    Media job processor adapter.
    
    Wraps MediaService to work with queue system.
    """
    
    def process(self, job_data: dict, db: Session) -> Dict[str, Any]:
        """
        Process a media job.
        
        Args:
            job_data: Job payload containing:
                - asset_ids: List of asset IDs to process
                - request_id: Request identifier
                - owner: Optional owner
            db: Database session
            
        Returns:
            Dictionary with processing results
        """
        try:
            asset_ids = job_data.get("asset_ids", [])
            request_id = job_data.get("request_id")
            owner = job_data.get("owner")
            
            if not asset_ids:
                raise ValueError("No asset IDs provided in job data")
            if not request_id:
                raise ValueError("No request_id provided in job data")
            
            # Get storage adapter
            storage = get_storage_adapter()
            
            # Create media service
            service = MediaService(db, storage)
            
            # Process each asset
            results = []
            for asset_id_str in asset_ids:
                try:
                    asset_id = UUID(asset_id_str)
                    result = service.process_asset(asset_id, request_id)
                    results.append(result)
                    logger.info(
                        f"Processed asset {asset_id} for request {request_id}. "
                        f"Cluster: {result.get('cluster_id')}"
                    )
                except Exception as e:
                    logger.error(f"Failed to process asset {asset_id_str}: {e}", exc_info=True)
                    results.append({
                        "success": False,
                        "asset_id": asset_id_str,
                        "error": str(e)
                    })
            
            # Update job with results
            from src.catalog.models import Job
            job_id_str = job_data.get("job_id")
            if job_id_str:
                job_id = UUID(job_id_str)
                job = db.query(Job).filter(Job.id == job_id).first()
                if job:
                    # Update asset_ids if needed
                    successful_asset_ids = [
                        UUID(r["asset_id"]) for r in results if r.get("success")
                    ]
                    if successful_asset_ids:
                        job.asset_ids = successful_asset_ids
                    db.commit()
            
            successful_count = sum(1 for r in results if r.get("success"))
            logger.info(
                f"Processed {successful_count}/{len(results)} media assets for request {request_id}"
            )
            
            return {
                "success": True,
                "results": results,
                "processed_count": successful_count,
                "total_count": len(results)
            }
            
        except MediaServiceError as e:
            logger.error(f"Media processing error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing media job: {e}", exc_info=True)
            raise

