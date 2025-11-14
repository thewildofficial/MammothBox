"""
Database models for the Automated File Allocator catalog.

This module defines all SQLAlchemy ORM models for tracking assets,
schemas, clusters, and lineage information.
"""

from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import (  # type: ignore
    Column, String, BigInteger, DateTime, Text, Float, Boolean,
    CheckConstraint, ForeignKey, Integer, JSON, Enum as SQLEnum, Index
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY  # type: ignore
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column  # type: ignore
from pgvector.sqlalchemy import Vector  # type: ignore


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class AssetRaw(Base):
    """
    Immutable record of raw uploaded content.

    Stores the original uploaded data before any processing, ensuring
    auditability and the ability to replay processing if needed.
    """
    __tablename__ = "asset_raw"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True)
    part_id: Mapped[str] = mapped_column(String(255), nullable=False)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False)

    # Relationship to processed asset
    assets: Mapped[List["Asset"]] = relationship(
        "Asset", back_populates="raw_asset")

    __table_args__ = (
        Index('idx_asset_raw_request_id', 'request_id'),
    )


class Asset(Base):
    """
    Canonical metadata for processed assets.

    Contains embeddings, tags, cluster assignments, and schema references
    for both media files and JSON documents.
    """
    __tablename__ = "asset"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(
        SQLEnum('media', 'json', 'document', name='asset_kind'),
        nullable=False
    )
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True)
    content_type: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True)
    parent_asset_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Processing status
    status: Mapped[str] = mapped_column(
        SQLEnum('queued', 'processing', 'done', 'failed', name='asset_status'),
        default='queued',
        nullable=False,
        index=True
    )

    # Media-specific fields
    cluster_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cluster.id"), nullable=True, index=True)
    tags: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String), nullable=True)
    # Using Column for pgvector compatibility
    embedding = Column(Vector(512), nullable=True)

    # JSON-specific fields
    schema_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schema_def.id"), nullable=True, index=True)

    # Flexible metadata storage (EXIF, VLM results, admin notes, etc.)
    metadata_json: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)

    # Reference to raw upload
    raw_asset_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_raw.id"), nullable=True)

    # Relationships
    raw_asset: Mapped[Optional["AssetRaw"]] = relationship(
        "AssetRaw", back_populates="assets")
    cluster: Mapped[Optional["Cluster"]] = relationship(
        "Cluster", back_populates="assets")
    schema: Mapped[Optional["SchemaDef"]] = relationship(
        "SchemaDef", back_populates="assets")
    lineage_entries: Mapped[List["Lineage"]] = relationship(
        "Lineage", back_populates="asset")
    parent: Mapped[Optional["Asset"]] = relationship(
        "Asset", remote_side=[id], back_populates="children"
    )
    children: Mapped[List["Asset"]] = relationship(
        "Asset", back_populates="parent", cascade="all, delete-orphan"
    )
    document_chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="asset", cascade="all, delete-orphan"
    )
    __table_args__ = (
        CheckConstraint("kind IN ('media', 'json', 'document')", name='asset_kind_check'),
        CheckConstraint(
            "status IN ('queued', 'processing', 'done', 'failed')", name='asset_status_check'),
        Index('idx_asset_kind', 'kind'),
        Index('idx_asset_status', 'status'),
        Index('idx_asset_owner', 'owner'),
        Index('idx_asset_sha256', 'sha256'),
        Index('idx_asset_tags', 'tags', postgresql_using='gin'),
    )



class Cluster(Base):
    """
    Media clusters for organizing similar content.

    Stores centroid vectors and thresholds for automatic clustering
    of media files based on CLIP embeddings.
    """
    __tablename__ = "cluster"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    centroid = Column(Vector(512), nullable=True)
    threshold: Mapped[float] = mapped_column(
        Float, default=0.72, nullable=False)  # Default per spec
    provisional: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False)
    cluster_metadata_json: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSON, nullable=True)  # VLM cluster info, admin notes
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    assets: Mapped[List["Asset"]] = relationship(
        "Asset", back_populates="cluster")

    __table_args__ = (
        Index('idx_cluster_name', 'name'),
        Index('idx_cluster_provisional', 'provisional'),
    )



class SchemaDef(Base):
    """
    JSON schema definitions and storage decisions.

    Tracks schema proposals, storage choice (SQL vs JSONB), generated DDL,
    and approval status for JSON document storage.
    """
    __tablename__ = "schema_def"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    structure_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True)
    storage_choice: Mapped[str] = mapped_column(
        SQLEnum('sql', 'jsonb', name='storage_choice'),
        nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    ddl: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Schema proposal status
    status: Mapped[str] = mapped_column(
        SQLEnum('provisional', 'active', 'rejected', name='schema_status'),
        default='provisional',
        nullable=False,
        index=True
    )

    # Schema analysis metadata
    sample_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    field_stability: Mapped[Optional[float]
                            ] = mapped_column(Float, nullable=True)
    max_depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    top_level_keys: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True)

    # Decision rationale
    decision_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Who approved/rejected
    reviewed_by: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True)
    reviewed_at: Mapped[Optional[datetime]
                        ] = mapped_column(DateTime, nullable=True)

    # Relationships
    assets: Mapped[List["Asset"]] = relationship(
        "Asset", back_populates="schema")
    lineage_entries: Mapped[List["Lineage"]] = relationship(
        "Lineage", back_populates="schema")

    __table_args__ = (
        CheckConstraint("storage_choice IN ('sql', 'jsonb')",
                        name='storage_choice_check'),
        CheckConstraint(
            "status IN ('provisional', 'active', 'rejected')", name='schema_status_check'),
        Index('idx_schema_status', 'status'),
        Index('idx_schema_structure_hash', 'structure_hash'),
    )


class Lineage(Base):
    """
    Audit trail for asset processing.

    Tracks every stage of processing for complete observability and
    debugging of the ingestion pipeline.
    """
    __tablename__ = "lineage"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True)
    asset_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset.id"), nullable=True, index=True)
    schema_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schema_def.id"), nullable=True, index=True)

    # Processing stage information
    stage: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    detail: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Success/failure tracking
    success: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    asset: Mapped[Optional["Asset"]] = relationship(
        "Asset", back_populates="lineage_entries")
    schema: Mapped[Optional["SchemaDef"]] = relationship(
        "SchemaDef", back_populates="lineage_entries")

    __table_args__ = (
        Index('idx_lineage_request_id', 'request_id'),
        Index('idx_lineage_asset_id', 'asset_id'),
        Index('idx_lineage_stage', 'stage'),
        Index('idx_lineage_created_at', 'created_at'),
    )


class VideoFrame(Base):
    """
    Per-frame embeddings for video assets.

    Enables frame-level semantic search within videos.
    """
    __tablename__ = "video_frame"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset.id"), nullable=False, index=True)
    frame_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding = Column(Vector(512), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_video_frame_asset_id', 'asset_id'),
        Index('idx_video_frame_timestamp', 'timestamp_ms'),
    )


class Job(Base):
    """
    Job queue tracking for async processing.

    Tracks job status, retries, and dead-letter queue assignments
    for background processing of media and JSON assets.
    """
    __tablename__ = "job"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True)

    # Job metadata
    job_type: Mapped[str] = mapped_column(
        SQLEnum('media', 'json', name='job_type'),
        nullable=False,
        index=True
    )
    status: Mapped[str] = mapped_column(
        SQLEnum('queued', 'processing', 'done', 'failed', name='job_status'),
        default='queued',
        nullable=False,
        index=True
    )

    # Job payload (JSONB for flexibility)
    job_data: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True)

    # Dead-letter queue
    dead_letter: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Related assets (for status tracking)
    asset_ids: Mapped[Optional[List[UUID]]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("job_type IN ('media', 'json')",
                        name='job_type_check'),
        CheckConstraint(
            "status IN ('queued', 'processing', 'done', 'failed')", name='job_status_check'),
        # Note: request_id unique constraint creates index automatically, so idx_job_request_id is redundant
        Index('idx_job_status', 'status'),
        Index('idx_job_type', 'job_type'),
        Index('idx_job_dead_letter', 'dead_letter'),
        Index('idx_job_next_retry_at', 'next_retry_at'),
        Index('idx_job_created_at', 'created_at'),
    )


class DocumentChunk(Base):
    """Text chunks extracted from document assets."""

    __tablename__ = "document_chunk"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    asset_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset.id"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    parent_heading: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    element_type: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding = Column(Vector(768), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    asset: Mapped["Asset"] = relationship("Asset", back_populates="document_chunks")

    __table_args__ = (
        Index("idx_document_chunk_asset_id", "asset_id"),
        Index("idx_document_chunk_chunk_index", "chunk_index"),
    )


class IngestionBatch(Base):
    """
    Batch ingestion tracking for recursive folder uploads.
    
    Tracks progress of bulk folder ingestion operations, allowing
    users to monitor status and troubleshoot failures.
    """
    __tablename__ = 'ingestion_batch'
    
    batch_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    folder_path: Mapped[str] = mapped_column(String(500), nullable=False)
    
    # Batch status tracking
    status: Mapped[str] = mapped_column(
        SQLEnum('pending', 'processing', 'completed', 'failed', name='batch_status'),
        default='pending',
        nullable=False,
        index=True
    )
    
    # Progress counters
    total_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failed_files: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )
    
    # Metadata
    user_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name='batch_status_check'
        ),
        Index('idx_ingestion_batch_status', 'status'),
        Index('idx_ingestion_batch_owner', 'owner'),
        Index('idx_ingestion_batch_created_at', 'created_at'),
    )
