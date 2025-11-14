"""Ingestion orchestrator for unified file and JSON ingestion."""

import json
import hashlib
from uuid import uuid4, UUID
from typing import List, Optional, Dict, Any
from datetime import datetime
from io import BytesIO

from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.catalog.models import AssetRaw, Asset, Job, Lineage
from src.ingest.validator import IngestValidator, FileValidationResult, JsonValidationResult
from src.storage.factory import get_storage_adapter
from src.queue.manager import get_queue_backend
from src.queue.interface import QueueMessage


class OrchestrationError(Exception):
    pass


class IngestionOrchestrator:
    """Orchestrates the ingestion process."""

    def __init__(self, db: Session):
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
        """Orchestrate ingestion of files and/or JSON payload."""
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
        validation_results = self.validator.validate_request(
            files=files, payload=payload)

        if not validation_results["valid"]:
            # Check if any errors are size limit violations
            has_size_limit_error = any(
                isinstance(err, dict) and err.get("error_type") == "size_limit"
                for err in validation_results["errors"]
            )

            if has_size_limit_error:
                # Build detailed error message for size limit violations
                size_errors = [
                    err for err in validation_results["errors"]
                    if isinstance(err, dict) and err.get("error_type") == "size_limit"
                ]
                error_details = []
                for err in size_errors:
                    detail_msg = err.get("message", "")
                    if err.get("max_size") is not None:
                        detail_msg += f" (limit: {err['max_size']} bytes, actual: {err.get('size_bytes', 'unknown')} bytes)"
                    error_details.append(detail_msg)

                raise HTTPException(
                    status_code=413,
                    detail={
                        "error": "Payload too large",
                        "message": "Request exceeds size limits",
                        "details": error_details
                    }
                )
            else:
                # All other validation failures return 400
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Validation failed",
                        "details": [
                            err.get("message", err) if isinstance(
                                err, dict) else err
                            for err in validation_results["errors"]
                        ]
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
        # Calculate json_count: treat dict as 1 document, list as len(list) documents
        json_count = 0
        if validation_results["json"] and validation_results["json"].parsed_data:
            parsed_data = validation_results["json"].parsed_data
            if isinstance(parsed_data, dict):
                json_count = 1
            elif isinstance(parsed_data, list):
                json_count = len(parsed_data)
            # else remains 0

        job_data = {
            "job_id": str(job_id),
            "request_id": request_id,
            "owner": owner,
            "comments": comments,
            "file_count": len(files) if files else 0,
            "json_count": json_count,
            # Include asset_ids in job_data
            "asset_ids": [str(aid) for aid in asset_ids],
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

        try:
            self.db.flush()
        except IntegrityError as e:
            # Handle race condition: another request with same request_id created job
            self.db.rollback()

            # Re-query the existing job
            existing_job = self.db.query(Job).filter(
                Job.request_id == request_id
            ).first()

            if existing_job:
                # Return existing job info (idempotency)
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
            else:
                # Unexpected integrity error
                raise HTTPException(
                    status_code=500,
                    detail=f"Database integrity error: {str(e)}"
                )

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
                # Placeholder, will be updated by processor
                uri=f"json://pending/{doc_hash}",
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
