# API routes

import json
from uuid import uuid4, UUID
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, Query, Depends, HTTPException, status, Request
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.catalog.database import get_db
from src.catalog.models import SchemaDef, Job, Asset, AssetRaw, Cluster
from src.ingest.orchestrator import IngestionOrchestrator

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

    - **files**: Media files (images, videos, audio) or any file type
    - **payload**: JSON object or array (as JSON string)
    - **owner**: Optional owner identifier
    - **comments**: Optional metadata/comments (used as hint for schema generation)
    - **idempotency_key**: Optional idempotency key for deduplication
    - **collection_name**: Optional hint for collection/table name (deprecated, use comments)

    Returns 202 Accepted immediately with job_id for async processing.
    
    Supports:
    - Single or batch media files
    - Single or batch JSON documents
    - Mixed media and JSON in same request
    """
    try:
        orchestrator = IngestionOrchestrator(db)
        result = orchestrator.ingest(
            files=files,
            payload=payload,
            owner=owner,
            comments=comments or collection_name,  # Support both for backward compat
            idempotency_key=idempotency_key
        )
        
        return IngestResponse(
            job_id=result["job_id"],
            system_ids=result["system_ids"],
            status=result["status"],
            message=f"Job {result['job_id']} accepted for processing"
        )
        
    except HTTPException:
        raise
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
def get_object(system_id: str, db: Session = Depends(get_db)):
    """
    Get canonical metadata for an asset by system ID.
    
    Returns complete asset metadata including:
    - Basic info (id, kind, uri, size, etc.)
    - Processing status
    - Cluster info (for media)
    - Schema info (for JSON)
    - Tags and metadata
    """
    try:
        asset_uuid = UUID(system_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid system ID format")
    
    # Query asset
    asset = db.query(Asset).filter(Asset.id == asset_uuid).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Build response based on asset kind
    response = {
        "id": str(asset.id),
        "kind": asset.kind,
        "uri": asset.uri if asset.uri and not asset.uri.startswith("json://pending") else None,  # Hide placeholder URIs
        "content_type": asset.content_type,
        "size_bytes": asset.size_bytes,
        "sha256": asset.sha256,
        "owner": asset.owner,
        "created_at": asset.created_at.isoformat(),
        "updated_at": asset.updated_at.isoformat(),
        "status": asset.status,
    }
    
    # Add kind-specific fields
    if asset.kind == "media":
        # Media-specific fields
        response["tags"] = asset.tags or []
        response["embedding"] = {
            "dimension": 512 if asset.embedding else None,
            "model": "clip-ViT-B-32" if asset.embedding else None
        }
        
        # Cluster info
        if asset.cluster_id:
            cluster = db.query(Cluster).filter(Cluster.id == asset.cluster_id).first()
            if cluster:
                response["cluster"] = {
                    "id": str(cluster.id),
                    "name": cluster.name,
                    "provisional": cluster.provisional
                }
        
        # Raw asset info
        if asset.raw_asset_id:
            raw_asset = db.query(AssetRaw).filter(AssetRaw.id == asset.raw_asset_id).first()
            if raw_asset:
                response["raw_asset"] = {
                    "id": str(raw_asset.id),
                    "uri": raw_asset.uri,
                    "request_id": raw_asset.request_id,
                    "part_id": raw_asset.part_id
                }
        
        # Metadata (stored as JSONB) - not in model yet, skip for now
        # if hasattr(asset, 'metadata') and asset.metadata:
        #     response["metadata"] = asset.metadata
    
    elif asset.kind == "json":
        # JSON-specific fields
        if asset.schema_id:
            schema = db.query(SchemaDef).filter(SchemaDef.id == asset.schema_id).first()
            if schema:
                response["schema"] = {
                    "id": str(schema.id),
                    "name": schema.name,
                    "storage_choice": schema.storage_choice,
                    "status": schema.status,
                    "ddl": schema.ddl
                }
        
        # Storage location - extract from URI if present
        if asset.uri:
            # URI format: "sql://table_name/hash" or "jsonb://collection_name/hash"
            if asset.uri.startswith("sql://"):
                parts = asset.uri.split("/")
                if len(parts) >= 2:
                    response["storage_location"] = parts[1]  # table name
            elif asset.uri.startswith("jsonb://"):
                parts = asset.uri.split("/")
                if len(parts) >= 2:
                    response["storage_location"] = parts[1]  # collection name
    
    return response


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
