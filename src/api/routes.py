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
from src.ingest.json_processor import JsonProcessor, JsonProcessingError
from src.admin.handlers import AdminHandlers, AdminError

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
        # Hide placeholder URIs
        "uri": asset.uri if asset.uri and not asset.uri.startswith("json://pending") else None,
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
            cluster = db.query(Cluster).filter(
                Cluster.id == asset.cluster_id).first()
            if cluster:
                response["cluster"] = {
                    "id": str(cluster.id),
                    "name": cluster.name,
                    "provisional": cluster.provisional
                }

        # Raw asset info
        if asset.raw_asset_id:
            raw_asset = db.query(AssetRaw).filter(
                AssetRaw.id == asset.raw_asset_id).first()
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
            schema = db.query(SchemaDef).filter(
                SchemaDef.id == asset.schema_id).first()
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
            # After splitting "sql://table_name/hash" by "/", we get ["sql:", "", "table_name", "hash"]
            # So parts[1] is empty and parts[2] is the table/collection name
            if asset.uri.startswith("sql://"):
                parts = asset.uri.split("/")
                if len(parts) >= 3:
                    response["storage_location"] = parts[2]  # table name
            elif asset.uri.startswith("jsonb://"):
                parts = asset.uri.split("/")
                if len(parts) >= 3:
                    response["storage_location"] = parts[2]  # collection name

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


@router.get("/search", response_model=dict, status_code=status.HTTP_200_OK)
def search_assets(
    query: str = Query(..., description="Search text query"),
    type: Optional[str] = Query(
        None, description="Filter by asset type: 'media' or 'json'"),
    limit: int = Query(10, ge=1, le=100, description="Max results (1-100)"),
    threshold: float = Query(
        0.5, ge=0.0, le=1.0, description="Min similarity score (0.0-1.0)"),
    owner: Optional[str] = Query(None, description="Filter by owner"),
    cluster_id: Optional[str] = Query(
        None, description="Filter by cluster ID"),
    tags: Optional[str] = Query(
        None, description="Filter by tags (comma-separated)"),
    db: Session = Depends(get_db)
):
    """
    Semantic search for assets using CLIP embeddings.

    Performs text-to-image/video search by encoding the query text
    and finding assets with similar embeddings using pgvector ANN search.

    **Query Parameters:**
    - **query** (required): Text search query
    - **type**: Filter by 'media' or 'json'
    - **limit**: Max results (default: 10, max: 100)
    - **threshold**: Min similarity score (default: 0.5, range: 0.0-1.0)
    - **owner**: Filter by owner
    - **cluster_id**: Filter by cluster UUID
    - **tags**: Comma-separated tags (e.g., "cat,animal")

    **Returns:**
    - **query**: Original query text
    - **results**: Array of matching assets with similarity scores
    - **total**: Number of results
    - **query_time_ms**: Query execution time in milliseconds
    - **filters_applied**: Summary of applied filters

    **Example:**
    ```
    GET /api/v1/search?query=sunset&type=media&threshold=0.7&limit=20
    ```
    """
    from src.catalog.queries import QueryProcessor, SearchFilter, QueryError
    from uuid import UUID

    try:
        # Parse tags
        tag_list = None
        if tags:
            tag_list = [t.strip() for t in tags.split(',') if t.strip()]

        # Parse cluster_id
        cluster_uuid = None
        if cluster_id:
            try:
                cluster_uuid = UUID(cluster_id)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid cluster_id format. Must be a valid UUID."
                )

        # Build search filters
        filters = SearchFilter(
            asset_type=type,
            owner=owner,
            cluster_id=cluster_uuid,
            tags=tag_list,
            min_similarity=threshold,
            limit=limit
        )

        # Execute search
        processor = QueryProcessor()
        response = processor.search(db, query, filters)

        # Format response
        return {
            "query": response.query,
            "results": [
                {
                    "id": r.asset_id,
                    "kind": r.kind,
                    "uri": r.uri,
                    "content_type": r.content_type,
                    "size_bytes": r.size_bytes,
                    "owner": r.owner,
                    "tags": r.tags,
                    "similarity_score": r.similarity_score,
                    "cluster": {
                        "id": r.cluster_id,
                        "name": r.cluster_name
                    } if r.cluster_id else None,
                    "thumbnail_uri": r.thumbnail_uri,
                    "created_at": r.created_at,
                    "metadata": r.metadata
                }
                for r in response.results
            ],
            "total": response.total,
            "query_time_ms": response.query_time_ms,
            "filters_applied": response.filters_applied
        }

    except QueryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Search endpoint error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


# ==================== Admin Operations (Phase 8) ====================

# Schema Management Endpoints

@router.get("/api/v1/admin/schemas")
def list_schemas(
    status: Optional[str] = Query(
        None, description="Filter by status (provisional, active, rejected)"),
    storage_choice: Optional[str] = Query(
        None, description="Filter by storage choice (sql, jsonb)"),
    db: Session = Depends(get_db)
):
    """
    List all schema proposals with filtering.

    Admin endpoint for reviewing schema proposals.
    """
    try:
        admin = AdminHandlers(db)
        schemas = admin.list_schemas(
            status=status, storage_choice=storage_choice)
        return {"schemas": schemas, "count": len(schemas)}
    except AdminError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list schemas: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to list schemas: {str(e)}")


@router.get("/api/v1/admin/schemas/pending")
def get_pending_schemas(db: Session = Depends(get_db)):
    """
    Get all provisional schemas awaiting review.

    Convenience endpoint for admin dashboard.
    """
    try:
        admin = AdminHandlers(db)
        schemas = admin.get_pending_schemas()
        return {"schemas": schemas, "count": len(schemas)}
    except AdminError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get pending schemas: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get pending schemas: {str(e)}")


@router.get("/api/v1/admin/schemas/{schema_id}")
def get_schema(schema_id: UUID, db: Session = Depends(get_db)):
    """
    Get detailed schema information.
    """
    try:
        admin = AdminHandlers(db)
        schema = admin.get_schema(schema_id)
        return schema
    except AdminError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get schema: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get schema: {str(e)}")


class SchemaApprovalRequest(BaseModel):
    reviewed_by: str
    table_name: Optional[str] = None


@router.post("/api/v1/admin/schemas/{schema_id}/approve")
def approve_schema(
    schema_id: UUID,
    request: SchemaApprovalRequest,
    db: Session = Depends(get_db)
):
    """
    Approve a provisional schema and execute DDL migration.

    This will:
    - Mark schema as active
    - Execute DDL to create tables
    - Migrate assets from JSONB to SQL tables
    """
    try:
        admin = AdminHandlers(db)
        schema = admin.approve_schema(
            schema_id=schema_id,
            reviewed_by=request.reviewed_by,
            table_name=request.table_name
        )
        return {
            "status": "approved",
            "schema": schema,
            "message": f"Schema '{schema['name']}' approved and DDL executed"
        }
    except AdminError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to approve schema: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to approve schema: {str(e)}")


class SchemaRejectionRequest(BaseModel):
    reviewed_by: str
    reason: str


@router.post("/api/v1/admin/schemas/{schema_id}/reject")
def reject_schema(
    schema_id: UUID,
    request: SchemaRejectionRequest,
    db: Session = Depends(get_db)
):
    """
    Reject a provisional schema.

    This will mark the schema as rejected and trigger re-analysis
    with updated hints.
    """
    try:
        admin = AdminHandlers(db)
        schema = admin.reject_schema(
            schema_id=schema_id,
            reviewed_by=request.reviewed_by,
            reason=request.reason
        )
        return {
            "status": "rejected",
            "schema": schema,
            "message": f"Schema '{schema['name']}' rejected"
        }
    except AdminError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to reject schema: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to reject schema: {str(e)}")


# Cluster Management Endpoints

@router.get("/api/v1/admin/clusters")
def list_clusters(
    provisional_only: bool = Query(
        False, description="Only return provisional clusters"),
    min_assets: Optional[int] = Query(
        None, description="Minimum asset count filter"),
    db: Session = Depends(get_db)
):
    """
    List all clusters with statistics.

    Admin endpoint for reviewing and managing clusters.
    """
    try:
        admin = AdminHandlers(db)
        clusters = admin.list_clusters(
            provisional_only=provisional_only,
            min_assets=min_assets
        )
        return {"clusters": clusters, "count": len(clusters)}
    except AdminError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list clusters: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to list clusters: {str(e)}")


@router.get("/api/v1/admin/clusters/statistics")
def get_cluster_statistics(db: Session = Depends(get_db)):
    """
    Get overall cluster statistics.

    Provides dashboard metrics for cluster health.
    """
    try:
        admin = AdminHandlers(db)
        stats = admin.get_cluster_statistics()
        return stats
    except AdminError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get cluster statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get cluster statistics: {str(e)}")


@router.get("/api/v1/admin/clusters/merge-candidates")
def get_merge_candidates(
    similarity_threshold: float = Query(
        0.85, description="Minimum centroid similarity"),
    db: Session = Depends(get_db)
):
    """
    Identify cluster pairs that could be merged.

    Analyzes centroid similarities to suggest potential merges.
    """
    try:
        admin = AdminHandlers(db)
        candidates = admin.identify_merge_candidates(
            similarity_threshold=similarity_threshold)

        return {
            "candidates": [
                {
                    "cluster1": c1,
                    "cluster2": c2,
                    "similarity": sim
                }
                for c1, c2, sim in candidates
            ],
            "count": len(candidates)
        }
    except AdminError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            f"Failed to identify merge candidates: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to identify merge candidates: {str(e)}")


@router.get("/api/v1/admin/clusters/{cluster_id}")
def get_cluster(cluster_id: UUID, db: Session = Depends(get_db)):
    """
    Get detailed cluster information with statistics.
    """
    try:
        admin = AdminHandlers(db)
        cluster = admin.get_cluster(cluster_id)
        return cluster
    except AdminError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get cluster: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get cluster: {str(e)}")


class ClusterRenameRequest(BaseModel):
    new_name: str
    performed_by: str


@router.post("/api/v1/admin/clusters/{cluster_id}/rename")
def rename_cluster(
    cluster_id: UUID,
    request: ClusterRenameRequest,
    db: Session = Depends(get_db)
):
    """
    Rename a cluster.
    """
    try:
        admin = AdminHandlers(db)
        cluster = admin.rename_cluster(
            cluster_id=cluster_id,
            new_name=request.new_name,
            performed_by=request.performed_by
        )
        return {
            "status": "renamed",
            "cluster": cluster,
            "message": f"Cluster renamed to '{request.new_name}'"
        }
    except AdminError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to rename cluster: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to rename cluster: {str(e)}")


class ClusterMergeRequest(BaseModel):
    source_cluster_ids: List[UUID]
    performed_by: str


@router.post("/api/v1/admin/clusters/{target_cluster_id}/merge")
def merge_clusters(
    target_cluster_id: UUID,
    request: ClusterMergeRequest,
    db: Session = Depends(get_db)
):
    """
    Merge multiple clusters into target cluster.

    This will:
    - Move all assets from source clusters to target
    - Recompute target centroid
    - Delete source clusters
    """
    try:
        admin = AdminHandlers(db)
        cluster = admin.merge_clusters(
            source_cluster_ids=request.source_cluster_ids,
            target_cluster_id=target_cluster_id,
            performed_by=request.performed_by
        )
        return {
            "status": "merged",
            "cluster": cluster,
            "message": f"Merged {len(request.source_cluster_ids)} clusters into target"
        }
    except AdminError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to merge clusters: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to merge clusters: {str(e)}")


class ClusterThresholdRequest(BaseModel):
    threshold: float
    performed_by: str
    re_evaluate: bool = False


@router.post("/api/v1/admin/clusters/{cluster_id}/threshold")
def update_cluster_threshold(
    cluster_id: UUID,
    request: ClusterThresholdRequest,
    db: Session = Depends(get_db)
):
    """
    Update cluster similarity threshold.
    """
    try:
        admin = AdminHandlers(db)
        cluster = admin.update_cluster_threshold(
            cluster_id=cluster_id,
            threshold=request.threshold,
            performed_by=request.performed_by,
            re_evaluate=request.re_evaluate
        )
        return {
            "status": "updated",
            "cluster": cluster,
            "message": f"Threshold updated to {request.threshold}"
        }
    except AdminError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update threshold: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to update threshold: {str(e)}")


class ClusterConfirmRequest(BaseModel):
    performed_by: str


@router.post("/api/v1/admin/clusters/{cluster_id}/confirm")
def confirm_cluster(
    cluster_id: UUID,
    request: ClusterConfirmRequest,
    db: Session = Depends(get_db)
):
    """
    Mark cluster as confirmed (non-provisional).
    """
    try:
        admin = AdminHandlers(db)
        cluster = admin.confirm_cluster(
            cluster_id=cluster_id,
            performed_by=request.performed_by
        )
        return {
            "status": "confirmed",
            "cluster": cluster,
            "message": f"Cluster '{cluster['name']}' confirmed"
        }
    except AdminError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to confirm cluster: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to confirm cluster: {str(e)}")


# Legacy endpoint (deprecated)
@router.patch("/clusters/{cluster_id}")
async def update_cluster(cluster_id: str, action: dict):
    """
    Admin operations on clusters (Phase 2: Media processing).

    DEPRECATED: Use /api/v1/admin/clusters endpoints instead.
    """
    return {
        "cluster_id": cluster_id,
        "status": "deprecated",
        "message": "Use /api/v1/admin/clusters endpoints instead"
    }
