"""
JSON Processor Service.

Main orchestrator for JSON document processing, schema analysis,
and storage coordination.
"""

import json
import hashlib
from uuid import uuid4, UUID
from typing import List, Dict, Any, Optional
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import text

from src.catalog.models import Asset, SchemaDef, Lineage
from src.ingest.schema_decider import SchemaDecider, SchemaDecision, StorageChoice
from src.ingest.ddl_generator import DDLGenerator
from src.config.settings import get_settings


class JsonProcessingError(Exception):
    """Exception raised during JSON processing."""
    pass


class JsonProcessor:
    """
    Processes JSON documents through analysis, decision, and storage.

    Coordinates the entire JSON ingestion pipeline from raw documents
    to stored data with appropriate schema decisions.
    """

    def __init__(self, db: Session):
        """
        Initialize JSON processor.

        Args:
            db: Database session
        """
        self.db = db
        self.settings = get_settings()
        self.decider = SchemaDecider()
        self.ddl_generator = DDLGenerator()

    def process_documents(
        self,
        documents: List[Dict[str, Any]],
        request_id: str,
        owner: Optional[str] = None,
        collection_name_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a batch of JSON documents.

        Args:
            documents: List of JSON documents to process
            request_id: Unique request identifier for tracking
            owner: Optional owner identifier
            collection_name_hint: Optional hint for collection/table name

        Returns:
            Dictionary with processing results
        """
        try:
            # Log start of processing
            self._log_lineage(
                request_id=request_id,
                stage="json_processing_start",
                detail={"document_count": len(documents)},
                success=True
            )

            # Step 1: Analyze documents and make schema decision
            decision = self.decider.decide(documents)

            self._log_lineage(
                request_id=request_id,
                stage="schema_analysis",
                detail=decision.to_dict(),
                success=True
            )

            # Step 2: Find or create schema definition
            schema_def = self._find_or_create_schema(
                decision=decision,
                request_id=request_id,
                collection_name_hint=collection_name_hint
            )

            # Step 3: Store documents based on storage choice
            asset_ids = []

            if decision.storage_choice == StorageChoice.SQL:
                asset_ids = self._process_sql_documents(
                    documents=documents,
                    schema_def=schema_def,
                    request_id=request_id,
                    owner=owner
                )
            else:  # JSONB
                asset_ids = self._process_jsonb_documents(
                    documents=documents,
                    schema_def=schema_def,
                    request_id=request_id,
                    owner=owner
                )

            self._log_lineage(
                request_id=request_id,
                stage="json_processing_complete",
                detail={
                    "asset_ids": [str(aid) for aid in asset_ids],
                    "storage_choice": decision.storage_choice.value
                },
                success=True
            )

            return {
                "success": True,
                "asset_ids": asset_ids,
                "schema_id": schema_def.id,
                "storage_choice": decision.storage_choice.value,
                "status": schema_def.status,
            }

        except Exception as e:
            self._log_lineage(
                request_id=request_id,
                stage="json_processing_error",
                detail={"error": str(e)},
                success=False,
                error_message=str(e)
            )
            raise JsonProcessingError(f"Failed to process JSON documents: {e}")

    def _find_or_create_schema(
        self,
        decision: SchemaDecision,
        request_id: str,
        collection_name_hint: Optional[str] = None
    ) -> SchemaDef:
        """
        Find existing schema or create new provisional schema.

        Args:
            decision: Schema decision result
            request_id: Request ID for lineage
            collection_name_hint: Optional name hint

        Returns:
            SchemaDef instance
        """
        # Check if schema with this structure hash already exists
        existing_schema = self.db.query(SchemaDef).filter(
            SchemaDef.structure_hash == decision.structure_hash
        ).first()

        if existing_schema:
            self._log_lineage(
                request_id=request_id,
                schema_id=existing_schema.id,
                stage="schema_reused",
                detail={"schema_id": str(existing_schema.id)},
                success=True
            )
            return existing_schema

        # Generate collection/table name
        collection_name = self.decider.generate_collection_name(
            decision,
            hint=collection_name_hint
        )

        # Generate DDL based on storage choice
        if decision.storage_choice == StorageChoice.SQL:
            ddl = self.ddl_generator.generate_table_ddl(
                collection_name, decision)
        else:
            ddl = self.ddl_generator.generate_jsonb_collection_ddl(
                collection_name)

        # Create new schema definition
        schema_def = SchemaDef(
            id=uuid4(),
            name=collection_name,
            structure_hash=decision.structure_hash,
            storage_choice=decision.storage_choice.value,
            ddl=ddl,
            status="provisional" if not self.settings.auto_migrate else "active",
            sample_size=decision.documents_analyzed,
            field_stability=decision.field_stability,
            max_depth=decision.max_depth,
            top_level_keys=decision.top_level_keys,
            decision_reason=decision.reason,
        )

        self.db.add(schema_def)
        self.db.commit()

        self._log_lineage(
            request_id=request_id,
            schema_id=schema_def.id,
            stage="schema_created",
            detail={
                "schema_id": str(schema_def.id),
                "status": schema_def.status,
                "storage_choice": schema_def.storage_choice
            },
            success=True
        )

        # If auto-migrate is enabled and schema is active, execute DDL
        if schema_def.status == "active":
            self._execute_ddl(schema_def)

        return schema_def

    def _execute_ddl(self, schema_def: SchemaDef) -> None:
        """
        Execute DDL to create table/collection.

        Args:
            schema_def: Schema definition with DDL
        """
        if not schema_def.ddl:
            raise JsonProcessingError("Schema definition has no DDL")

        try:
            # Execute DDL
            # Replace placeholder with actual table name
            ddl = schema_def.ddl.replace("{table_name}", schema_def.name)
            self.db.execute(text(ddl))
            self.db.commit()
        except Exception as e:
            raise JsonProcessingError(f"Failed to execute DDL: {e}")

    def _process_sql_documents(
        self,
        documents: List[Dict[str, Any]],
        schema_def: SchemaDef,
        request_id: str,
        owner: Optional[str] = None
    ) -> List[UUID]:
        """
        Process documents for SQL storage.

        Args:
            documents: JSON documents to store
            schema_def: Schema definition
            request_id: Request ID for tracking
            owner: Optional owner

        Returns:
            List of created asset IDs
        """
        asset_ids = []

        # Note: Actual SQL insertion would happen here
        # For now, we just create asset records
        for doc in documents:
            # Calculate document hash
            doc_json = json.dumps(doc, sort_keys=True)
            doc_hash = hashlib.sha256(doc_json.encode()).hexdigest()

            # Create asset record
            asset = Asset(
                id=uuid4(),
                kind="json",
                uri=f"sql://{schema_def.name}/{doc_hash}",
                sha256=doc_hash,
                size_bytes=len(doc_json.encode()),
                owner=owner,
                status="done" if schema_def.status == "active" else "queued",
                schema_id=schema_def.id,
            )

            self.db.add(asset)
            asset_ids.append(asset.id)

        self.db.commit()
        return asset_ids

    def _process_jsonb_documents(
        self,
        documents: List[Dict[str, Any]],
        schema_def: SchemaDef,
        request_id: str,
        owner: Optional[str] = None
    ) -> List[UUID]:
        """
        Process documents for JSONB storage.

        Args:
            documents: JSON documents to store
            schema_def: Schema definition
            request_id: Request ID for tracking
            owner: Optional owner

        Returns:
            List of created asset IDs
        """
        asset_ids = []

        # Note: Actual JSONB insertion would happen here
        # For now, we just create asset records
        for doc in documents:
            # Calculate document hash
            doc_json = json.dumps(doc, sort_keys=True)
            doc_hash = hashlib.sha256(doc_json.encode()).hexdigest()

            # Create asset record
            asset = Asset(
                id=uuid4(),
                kind="json",
                uri=f"jsonb://{schema_def.name}/{doc_hash}",
                sha256=doc_hash,
                size_bytes=len(doc_json.encode()),
                owner=owner,
                status="done" if schema_def.status == "active" else "queued",
                schema_id=schema_def.id,
            )

            self.db.add(asset)
            asset_ids.append(asset.id)

        self.db.commit()
        return asset_ids

    def _log_lineage(
        self,
        request_id: str,
        stage: str,
        detail: Dict[str, Any],
        success: bool,
        asset_id: Optional[UUID] = None,
        schema_id: Optional[UUID] = None,
        error_message: Optional[str] = None
    ) -> None:
        """
        Log processing lineage for audit trail.

        Args:
            request_id: Request identifier
            stage: Processing stage name
            detail: Stage details
            success: Whether stage succeeded
            asset_id: Optional asset ID
            schema_id: Optional schema ID
            error_message: Optional error message
        """
        lineage = Lineage(
            id=uuid4(),
            request_id=request_id,
            asset_id=asset_id,
            schema_id=schema_id,
            stage=stage,
            detail=detail,
            success=success,
            error_message=error_message
        )
        self.db.add(lineage)
        self.db.commit()

    def approve_schema(self, schema_id: UUID, reviewed_by: str) -> SchemaDef:
        """
        Approve a provisional schema and execute DDL.

        Args:
            schema_id: ID of schema to approve
            reviewed_by: Identifier of reviewer

        Returns:
            Updated schema definition
        """
        schema_def = self.db.query(SchemaDef).filter(
            SchemaDef.id == schema_id).first()

        if not schema_def:
            raise JsonProcessingError(f"Schema {schema_id} not found")

        if schema_def.status != "provisional":
            raise JsonProcessingError(
                f"Schema {schema_id} is not provisional (status: {schema_def.status})")

        # Update schema status
        schema_def.status = "active"
        schema_def.reviewed_by = reviewed_by
        schema_def.reviewed_at = datetime.utcnow()

        # Execute DDL to create table
        self._execute_ddl(schema_def)

        # Update all pending assets for this schema
        self.db.query(Asset).filter(
            Asset.schema_id == schema_id,
            Asset.status == "queued"
        ).update({"status": "processing"})

        self.db.commit()
        return schema_def

    def reject_schema(self, schema_id: UUID, reviewed_by: str, reason: str) -> SchemaDef:
        """
        Reject a provisional schema.

        Args:
            schema_id: ID of schema to reject
            reviewed_by: Identifier of reviewer
            reason: Rejection reason

        Returns:
            Updated schema definition
        """
        schema_def = self.db.query(SchemaDef).filter(
            SchemaDef.id == schema_id).first()

        if not schema_def:
            raise JsonProcessingError(f"Schema {schema_id} not found")

        if schema_def.status != "provisional":
            raise JsonProcessingError(f"Schema {schema_id} is not provisional")

        # Update schema status
        schema_def.status = "rejected"
        schema_def.reviewed_by = reviewed_by
        schema_def.reviewed_at = datetime.utcnow()
        schema_def.decision_reason = f"{schema_def.decision_reason}\n\nRejection reason: {reason}"

        # Mark all pending assets as failed
        self.db.query(Asset).filter(
            Asset.schema_id == schema_id,
            Asset.status == "queued"
        ).update({"status": "failed"})

        self.db.commit()
        return schema_def
