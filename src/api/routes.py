# API routes

import json
from uuid import uuid4
from fastapi import APIRouter, UploadFile, File, Form, Query, Depends, HTTPException
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.catalog.database import get_db
from src.catalog.models import SchemaDef
from src.ingest.json_processor import JsonProcessor, JsonProcessingError

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


@router.post("/ingest", response_model=IngestResponse)
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

    - **files**: Media files (images, videos, audio)
    - **payload**: JSON object or array (as JSON string)
    - **owner**: Optional owner identifier
    - **comments**: Optional metadata/comments (used as hint for schema generation)
    - **idempotency_key**: Optional idempotency key for deduplication
    - **collection_name**: Optional hint for collection/table name

    Returns:
        - **job_id**: Unique identifier for this ingestion request
        - **system_ids**: List of created asset IDs
        - **status**: Processing status
    """
    request_id = idempotency_key or str(uuid4())

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

        # Process JSON documents
        processor = JsonProcessor(db)
        result = processor.process_documents(
            documents=documents,
            request_id=request_id,
            owner=owner,
            collection_name_hint=collection_name or comments
        )

        return IngestResponse(
            job_id=request_id,
            system_ids=[str(aid) for aid in result["asset_ids"]],
            status=result["status"],
            message=f"Processed {len(documents)} documents. Storage: {result['storage_choice']}"
        )

    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON payload: {str(e)}"
        )
    except JsonProcessingError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Processing error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )


@router.get("/ingest/{job_id}/status")
async def get_ingest_status(job_id: str):
    """Get processing status for an ingestion job (Phase 2: Queue integration)"""
    return {
        "job_id": job_id,
        "status": "queued",
        "progress": {
            "queued": 0,
            "processing": 0,
            "done": 0,
            "failed": 0
        }
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
