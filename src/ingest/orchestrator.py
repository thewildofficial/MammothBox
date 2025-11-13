"""
Ingestion orchestrator for unified file and JSON ingestion.

Coordinates the ingestion flow: validation, raw storage, asset creation,
lineage tracking, and job enqueueing.
"""

import json
import hashlib
from uuid import uuid4, UUID
from typing import List, Optional, Dict, Any
from datetime import datetime
from io import BytesIO

from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session

from src.catalog.models import AssetRaw, Asset, Job, Lineage
from src.ingest.validator import IngestValidator, FileValidationResult, JsonValidationResult
from src.storage.manager import get_storage_adapter
from src.queue.manager import get_queue_backend
from src.queue.interface import QueueMessage


class OrchestrationError(Exception):
    """Exception raised during orchestration."""
    pass


class IngestionOrchestrator:
    """
    Orchestrates the ingestion process.
    
    Handles validation, raw storage, asset creation, lineage tracking,
    and job enqueueing for both media files and JSON documents.
    """
    
    def __init__(self, db: Session):
        """
        Initialize orchestrator.
        
        Args:
            db: Database session
        """
        self.db = db
        self.validator = IngestValidator()
        self.storage = get_storage_adapter()
        self.queue = get_queue_backend()
    
    def ingest(
        self,
        files: Optional[List[UploadFile]] = None,
        payload: Optional[str] = None,
        owner: Optional[str] = None,
        comments: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Orchestrate ingestion of files and/or JSON payload.
        
        Args:
            files: Optional list of uploaded files
            payload: Optional JSON payload string
            owner: Optional owner identifier
            comments: Optional comments/metadata
            idempotency_key: Optional idempotency key for deduplication
            
        Returns:
            Dictionary with:
            - job_id: UUID of the created job
            - system_ids: List of asset UUIDs
            - request_id: Request identifier
            - status: "accepted"
            
        Raises:
            HTTPException: If validation or orchestration fails
        """
        # Generate request_id and job_id
        request_id = idempotency_key or str(uuid4())
        job_id = uuid4()
        
        # Check idempotency key if provided
        if idempotency_key:
            existing_job = self.db.query(Job).filter(
                Job.request_id == idempotency_key
            ).first()
            if existing_job:
                # Return existing job info
                existing_assets = self.db.query(Asset).filter(
                    Asset.id.in_(existing_job.asset_ids or [])
                ).all()
                return {
                    "job_id": str(existing_job.id),
                    "system_ids": [str(a.id) for a in existing_assets],
                    "status": "accepted",
                    "request_id": request_id,
                    "created_at": existing_job.created_at.isoformat(),
                    "message": "Duplicate request (idempotency key)"
                }
        
        # Validate request
        validation_results = self.validator.validate_request(files=files, payload=payload)
        
        if not validation_results["valid"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Validation failed",
                    "details": validation_results["errors"]
                }
            )
        
        # Process files and JSON
        asset_ids = []
        job_type = None
        
        # Process files
        if files:
            file_assets = self._process_files(
                files=files,
                request_id=request_id,
                owner=owner,
                validation_results=validation_results["files"]
            )
            asset_ids.extend(file_assets)
            if file_assets:
                job_type = "media"  # At least one media file
        
        # Process JSON payload
        if payload and validation_results["json"]:
            json_assets = self._process_json_payload(
                payload=payload,
                request_id=request_id,
                owner=owner,
                validation_result=validation_results["json"]
            )
            asset_ids.extend(json_assets)
            if json_assets:
                job_type = job_type or "json"  # Set if no media files
        
        if not asset_ids:
            raise HTTPException(
                status_code=400,
                detail="No valid assets to process"
            )
        
        # Create job record
        job_data = {
            "job_id": str(job_id),
            "request_id": request_id,
            "owner": owner,
            "comments": comments,
            "file_count": len(files) if files else 0,
            "json_count": len(validation_results["json"].parsed_data) if validation_results["json"] and validation_results["json"].parsed_data else 0,
        }
        
        # Add file metadata if present
        if files:
            job_data["files"] = [
                {
                    "filename": f.filename,
                    "content_type": f.content_type,
                    "size": validation_results["files"][i].size_bytes
                }
                for i, f in enumerate(files)
            ]
        
        # Add JSON data if present
        if payload and validation_results["json"]:
            job_data["json_payload"] = validation_results["json"].parsed_data
        
        job = Job(
            id=job_id,
            request_id=request_id,
            job_type=job_type or "json",  # Default to json if unclear
            status="queued",
            job_data=job_data,
            asset_ids=asset_ids
        )
        
        self.db.add(job)
        self.db.flush()
        
        # Log lineage for job creation
        self._log_lineage(
            request_id=request_id,
            stage="ingest_accepted",
            detail={
                "job_id": str(job_id),
                "asset_count": len(asset_ids),
                "job_type": job_type
            },
            success=True
        )
        
        # Enqueue job
        queue_message = QueueMessage(
            job_id=job_id,
            job_type=job_type or "json",
            job_data=job_data,
            priority=0,
            retry_count=0,
            max_retries=3,
            created_at=datetime.utcnow()
        )
        
        try:
            self.queue.enqueue(queue_message)
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to enqueue job: {str(e)}"
            )
        
        return {
            "job_id": str(job_id),
            "system_ids": [str(aid) for aid in asset_ids],
            "status": "accepted",
            "request_id": request_id,
            "created_at": datetime.utcnow().isoformat()
        }
    
    def _process_files(
        self,
        files: List[UploadFile],
        request_id: str,
        owner: Optional[str],
        validation_results: List[FileValidationResult]
    ) -> List[UUID]:
        """
        Process uploaded files: store raw bytes and create asset records.
        
        Args:
            files: List of uploaded files
            request_id: Request identifier
            owner: Optional owner
            validation_results: Validation results for each file
            
        Returns:
            List of created asset UUIDs
        """
        asset_ids = []
        
        for i, file in enumerate(files):
            validation_result = validation_results[i]
            
            if not validation_result.valid:
                # Skip invalid files but log error
                self._log_lineage(
                    request_id=request_id,
                    stage="file_validation_failed",
                    detail={
                        "filename": file.filename,
                        "error": validation_result.error
                    },
                    success=False,
                    error_message=validation_result.error
                )
                continue
            
            # Generate part_id and asset_id
            part_id = str(uuid4())
            asset_id = uuid4()
            
            # Store raw file
            try:
                # Read file content
                content = file.file.read()
                file.file.seek(0)
                
                # Store to storage backend
                filename = file.filename or f"file_{i}"
                uri = self.storage.store_raw(
                    request_id=request_id,
                    part_id=part_id,
                    file=BytesIO(content),
                    filename=filename
                )
                
                # Create AssetRaw record
                asset_raw = AssetRaw(
                    id=uuid4(),
                    request_id=request_id,
                    part_id=part_id,
                    uri=uri,
                    size_bytes=validation_result.size_bytes,
                    content_type=validation_result.content_type
                )
                self.db.add(asset_raw)
                
                # Create Asset record (placeholder, will be updated by processor)
                asset = Asset(
                    id=asset_id,
                    kind="media",
                    uri=uri,
                    sha256=validation_result.sha256,
                    content_type=validation_result.content_type,
                    size_bytes=validation_result.size_bytes,
                    owner=owner,
                    status="queued",
                    raw_asset_id=asset_raw.id
                )
                self.db.add(asset)
                asset_ids.append(asset_id)
                
                # Log lineage
                self._log_lineage(
                    request_id=request_id,
                    asset_id=asset_id,
                    stage="raw_stored",
                    detail={
                        "uri": uri,
                        "size_bytes": validation_result.size_bytes,
                        "content_type": validation_result.content_type
                    },
                    success=True
                )
                
            except Exception as e:
                self._log_lineage(
                    request_id=request_id,
                    stage="file_storage_failed",
                    detail={
                        "filename": file.filename,
                        "error": str(e)
                    },
                    success=False,
                    error_message=str(e)
                )
                # Continue with other files
                continue
        
        self.db.flush()
        return asset_ids
    
    def _process_json_payload(
        self,
        payload: str,
        request_id: str,
        owner: Optional[str],
        validation_result: JsonValidationResult
    ) -> List[UUID]:
        """
        Process JSON payload: create asset records.
        
        Args:
            payload: JSON payload string
            request_id: Request identifier
            owner: Optional owner
            validation_result: Validation result
            
        Returns:
            List of created asset UUIDs
        """
        if not validation_result.valid or not validation_result.parsed_data:
            return []
        
        asset_ids = []
        parsed_data = validation_result.parsed_data
        
        # Normalize to list
        if isinstance(parsed_data, dict):
            documents = [parsed_data]
        else:
            documents = parsed_data
        
        for doc in documents:
            asset_id = uuid4()
            
            # Compute document hash
            doc_json = json.dumps(doc, sort_keys=True)
            doc_hash = hashlib.sha256(doc_json.encode()).hexdigest()
            
            # Create Asset record (placeholder, will be updated by processor)
            # Note: URI is required by model, so we use a placeholder that will be updated
            asset = Asset(
                id=asset_id,
                kind="json",
                uri=f"json://pending/{doc_hash}",  # Placeholder, will be updated by processor
                sha256=doc_hash,
                content_type="application/json",
                size_bytes=len(doc_json.encode()),
                owner=owner,
                status="queued"
            )
            self.db.add(asset)
            asset_ids.append(asset_id)
            
            # Log lineage
            self._log_lineage(
                request_id=request_id,
                asset_id=asset_id,
                stage="json_validated",
                detail={
                    "size_bytes": len(doc_json.encode()),
                    "is_batch": validation_result.is_batch
                },
                success=True
            )
        
        self.db.flush()
        return asset_ids
    
    def _log_lineage(
        self,
        request_id: str,
        stage: str,
        detail: Dict[str, Any],
        success: bool,
        asset_id: Optional[UUID] = None,
        error_message: Optional[str] = None
    ) -> None:
        """
        Log lineage entry.
        
        Args:
            request_id: Request identifier
            stage: Processing stage
            detail: Stage details
            success: Whether stage succeeded
            asset_id: Optional asset ID
            error_message: Optional error message
        """
        lineage = Lineage(
            id=uuid4(),
            request_id=request_id,
            asset_id=asset_id,
            stage=stage,
            detail=detail,
            success=success,
            error_message=error_message
        )
        self.db.add(lineage)
        # Don't commit here, let caller handle transaction

