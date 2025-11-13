# API routes

import json
from uuid import uuid4, UUID
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, Query, Depends, HTTPException, status
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.catalog.database import get_db
from src.catalog.models import SchemaDef, Job, Asset
from src.queue.manager import get_queue_backend
from src.queue.interface import QueueMessage

router = APIRouter()


class IngestResponse(BaseModel):
    job_id: str
    system_ids: List[str]
    status: str
    message: Optional[str] = None


class SearchResponse(BaseModel):
    results: List[dict]


class SchemaResponse(BaseModel):
    id: str
    name: str
    storage_choice: str
    status: str
    created_at: str
    ddl: Optional[str] = None
    decision_reason: Optional[str] = None


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest(
    files: Optional[List[UploadFile]] = File(None),
    payload: Optional[str] = Form(None),
    owner: Optional[str] = Form(None),
    comments: Optional[str] = Form(None),
    idempotency_key: Optional[str] = Form(None),
    collection_name: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Unified ingestion endpoint for media files and JSON documents.

    - **files**: Media files (images, videos, audio) - not yet implemented
    - **payload**: JSON object or array (as JSON string)
    - **owner**: Optional owner identifier
    - **comments**: Optional metadata/comments (used as hint for schema generation)
    - **idempotency_key**: Optional idempotency key for deduplication
    - **collection_name**: Optional hint for collection/table name

    Returns 202 Accepted immediately with job_id for async processing.
    """
    request_id = idempotency_key or str(uuid4())
    job_id = uuid4()

    # For now, only handle JSON payloads (media processing is separate)
    if not payload:
        raise HTTPException(
            status_code=400,
            detail="No payload provided. For JSON ingestion, provide 'payload' parameter."
        )

    try:
        # Parse JSON payload
        parsed_payload = json.loads(payload)

        # Ensure payload is a list
        if isinstance(parsed_payload, dict):
            documents = [parsed_payload]
        elif isinstance(parsed_payload, list):
            documents = parsed_payload
        else:
            raise HTTPException(
                status_code=400,
                detail="Payload must be a JSON object or array"
            )

        # Create job record (assets will be created during processing)
        job = Job(
            id=job_id,
            request_id=request_id,
            job_type="json",
            status="queued",
            job_data={
                "job_id": str(job_id),  # Include for processor to update asset_ids
                "documents": documents,
                "request_id": request_id,
                "owner": owner,
                "collection_name_hint": collection_name or comments
            },
            asset_ids=None  # Will be updated after processing
        )
        db.add(job)
        # Flush to get the job ID but don't commit yet
        db.flush()
        
        # Build queue message from in-memory job data
        queue_backend = get_queue_backend()
        queue_message = QueueMessage(
            job_id=job_id,
            job_type="json",
            job_data=job.job_data,
            priority=0,
            retry_count=0,
            max_retries=3,
            created_at=datetime.utcnow()
        )
        
        # Enqueue job before committing to avoid orphan jobs if enqueue fails
        # If enqueue fails, the transaction will rollback
        try:
            queue_backend.enqueue(queue_message)
            # Only commit after successful enqueue
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to enqueue job: {str(e)}"
            )

        return IngestResponse(
            job_id=str(job_id),
            system_ids=[],  # Will be populated after processing
            status="accepted",
            message=f"Job queued for processing {len(documents)} documents"
        )

    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON payload: {str(e)}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )


@router.get("/ingest/{job_id}/status")
def get_ingest_status(job_id: str, db: Session = Depends(get_db)):
    """
    Get processing status for an ingestion job.
    
    Returns real-time status including per-asset progress.
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    
    # Query job
    job = db.query(Job).filter(Job.id == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Query related assets
    assets = []
    if job.asset_ids:
        assets = db.query(Asset).filter(Asset.id.in_(job.asset_ids)).all()
    
    # Calculate progress
    status_counts = {"queued": 0, "processing": 0, "done": 0, "failed": 0}
    asset_statuses = []
    
    for asset in assets:
        # Use .get() with default to handle unexpected status values gracefully
        status_counts[asset.status] = status_counts.get(asset.status, 0) + 1
        asset_statuses.append({
            "system_id": str(asset.id),
            "status": asset.status,
            "cluster_id": str(asset.cluster_id) if asset.cluster_id else None,
            "schema_id": str(asset.schema_id) if asset.schema_id else None
        })
    
    # Determine overall status
    overall_status = job.status
    if overall_status == "done" and status_counts["failed"] > 0:
        overall_status = "partial"
    elif overall_status == "queued" and status_counts["processing"] > 0:
        overall_status = "processing"
    
    return {
        "job_id": job_id,
        "status": overall_status,
        "progress": {
            "queued": status_counts["queued"],
            "processing": status_counts["processing"],
            "done": status_counts["done"],
            "failed": status_counts["failed"],
            "total": len(assets)
        },
        "assets": asset_statuses,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "dead_letter": job.dead_letter,
        "error_message": job.error_message
    }


@router.get("/objects/{system_id}")
async def get_object(system_id: str):
    """Get asset metadata by system ID (Phase 2: Query implementation)"""
    return {"id": system_id, "status": "not_found"}


@router.get("/search", response_model=SearchResponse)
async def search(
    query: str = Query(..., description="Search query text"),
    type: Optional[str] = Query(
        None, description="Filter by type: media or json"),
    limit: int = Query(10, ge=1, le=100)
):
    """
    Semantic search for media files using CLIP embeddings (Phase 2: Media processing).

    Examples:
    - "dog" - finds all images/videos with dogs
    - "monkey with a hat" - finds specific compositions
    """
    return {"results": []}


@router.get("/schemas", response_model=List[SchemaResponse])
def list_schemas(
    status: Optional[str] = Query(
        None, description="Filter by status: provisional, active, rejected"),
    db: Session = Depends(get_db)
):
    """
    List all schema definitions.

    - **status**: Optional filter by schema status

    Returns list of schemas with their DDL and decision rationale.
    """
    query = db.query(SchemaDef)

    if status:
        query = query.filter(SchemaDef.status == status)

    schemas = query.order_by(SchemaDef.created_at.desc()).all()

    return [
        SchemaResponse(
            id=str(schema.id),
            name=schema.name,
            storage_choice=schema.storage_choice,
            status=schema.status,
            created_at=schema.created_at.isoformat(),
            ddl=schema.ddl,
            decision_reason=schema.decision_reason
        )
        for schema in schemas
    ]


@router.get("/schemas/{schema_id}", response_model=SchemaResponse)
def get_schema(schema_id: str, db: Session = Depends(get_db)):
    """Get details of a specific schema."""
    from uuid import UUID

    try:
        schema_uuid = UUID(schema_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid schema ID format")

    schema = db.query(SchemaDef).filter(SchemaDef.id == schema_uuid).first()

    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")

    return SchemaResponse(
        id=str(schema.id),
        name=schema.name,
        storage_choice=schema.storage_choice,
        status=schema.status,
        created_at=schema.created_at.isoformat(),
        ddl=schema.ddl,
        decision_reason=schema.decision_reason
    )


@router.post("/schemas/{schema_id}/approve")
def approve_schema(
    schema_id: str,
    reviewed_by: str = Form(..., description="Identifier of the reviewer"),
    db: Session = Depends(get_db)
):
    """
    Approve a provisional schema and execute DDL.

    - **schema_id**: UUID of the schema to approve
    - **reviewed_by**: Identifier of the person approving

    This will create the actual database table/collection and activate
    the schema for use.
    """
    from uuid import UUID

    try:
        schema_uuid = UUID(schema_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid schema ID format")

    try:
        processor = JsonProcessor(db)
        schema = processor.approve_schema(schema_uuid, reviewed_by)

        return {
            "success": True,
            "schema_id": str(schema.id),
            "status": schema.status,
            "message": f"Schema '{schema.name}' approved and DDL executed"
        }
    except JsonProcessingError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to approve schema: {str(e)}")


@router.post("/schemas/{schema_id}/reject")
def reject_schema(
    schema_id: str,
    reviewed_by: str = Form(..., description="Identifier of the reviewer"),
    reason: str = Form(..., description="Reason for rejection"),
    db: Session = Depends(get_db)
):
    """
    Reject a provisional schema.

    - **schema_id**: UUID of the schema to reject
    - **reviewed_by**: Identifier of the person rejecting
    - **reason**: Explanation for rejection

    This will mark the schema as rejected and fail any pending assets.
    """
    from uuid import UUID

    try:
        schema_uuid = UUID(schema_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid schema ID format")

    try:
        processor = JsonProcessor(db)
        schema = processor.reject_schema(schema_uuid, reviewed_by, reason)

        return {
            "success": True,
            "schema_id": str(schema.id),
            "status": schema.status,
            "message": f"Schema '{schema.name}' rejected"
        }
    except JsonProcessingError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to reject schema: {str(e)}")


@router.patch("/clusters/{cluster_id}")
async def update_cluster(cluster_id: str, action: dict):
    """
    Admin operations on clusters (Phase 2: Media processing):
    - Rename cluster
    - Merge clusters
    - Adjust thresholds
    """
    return {"cluster_id": cluster_id, "status": "updated"}
