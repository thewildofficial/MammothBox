"""
Edge case tests for JSON processor.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4
from sqlalchemy.orm import Session

from src.ingest.json_processor import JsonProcessor, JsonProcessingError
from src.catalog.models import SchemaDef, Asset
from src.ingest.schema_decider import StorageChoice


class TestJsonProcessorEdgeCases:
    """Edge case tests for JSON processor."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = MagicMock(spec=Session)
        db.query = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.flush = MagicMock()
        db.rollback = MagicMock()
        db.execute = MagicMock()
        return db

    @pytest.fixture
    def processor(self, mock_db):
        """Create a JsonProcessor instance."""
        return JsonProcessor(mock_db)

    def test_process_empty_document_list(self, processor):
        """Test processing empty document list."""
        with pytest.raises(Exception):
            processor.process_documents(
                documents=[],
                request_id="test-request"
            )

    def test_process_single_document(self, processor, mock_db):
        """Test processing single document."""
        # Mock schema decision and creation
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with patch.object(processor.decider, 'decide') as mock_decide, \
             patch.object(processor, '_find_or_create_schema') as mock_find_schema, \
             patch.object(processor, '_process_sql_documents') as mock_process:
            
            from src.ingest.schema_decider import SchemaDecision
            mock_decision = SchemaDecision(
                storage_choice=StorageChoice.SQL,
                confidence=0.9,
                reason="Test",
                documents_analyzed=1,
                top_level_keys=1,
                max_depth=1,
                field_stability=1.0,
                type_stability=1.0,
                has_array_of_objects=False,
                structure_hash="test_hash",
                fields={}
            )
            mock_decide.return_value = mock_decision
            
            mock_schema = SchemaDef(
                id=uuid4(),
                name="test_table",
                structure_hash="test_hash",
                storage_choice="sql",
                status="provisional"
            )
            mock_find_schema.return_value = mock_schema
            mock_process.return_value = [uuid4()]
            
            result = processor.process_documents(
                documents=[{"id": 1}],
                request_id="test-request"
            )
            
            assert result["success"] is True
            assert len(result["asset_ids"]) == 1

    def test_process_with_existing_schema(self, processor, mock_db):
        """Test processing when schema already exists."""
        existing_schema = SchemaDef(
            id=uuid4(),
            name="existing_table",
            structure_hash="existing_hash",
            storage_choice="sql",
            status="active"
        )
        
        mock_db.query.return_value.filter.return_value.first.return_value = existing_schema
        
        with patch.object(processor.decider, 'decide') as mock_decide, \
             patch.object(processor, '_process_sql_documents') as mock_process:
            
            from src.ingest.schema_decider import SchemaDecision
            mock_decision = SchemaDecision(
                storage_choice=StorageChoice.SQL,
                confidence=0.9,
                reason="Test",
                documents_analyzed=1,
                top_level_keys=1,
                max_depth=1,
                field_stability=1.0,
                type_stability=1.0,
                has_array_of_objects=False,
                structure_hash="existing_hash",
                fields={}
            )
            mock_decide.return_value = mock_decision
            mock_process.return_value = [uuid4()]
            
            result = processor.process_documents(
                documents=[{"id": 1}],
                request_id="test-request"
            )
            
            # Should reuse existing schema
            assert result["schema_id"] == existing_schema.id

    def test_process_jsonb_documents(self, processor, mock_db):
        """Test processing JSONB documents."""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with patch.object(processor.decider, 'decide') as mock_decide, \
             patch.object(processor, '_find_or_create_schema') as mock_find_schema, \
             patch.object(processor, '_process_jsonb_documents') as mock_process:
            
            from src.ingest.schema_decider import SchemaDecision
            mock_decision = SchemaDecision(
                storage_choice=StorageChoice.JSONB,
                confidence=0.9,
                reason="Test",
                documents_analyzed=1,
                top_level_keys=1,
                max_depth=1,
                field_stability=0.5,
                type_stability=1.0,
                has_array_of_objects=False,
                structure_hash="test_hash",
                fields={}
            )
            mock_decide.return_value = mock_decision
            
            mock_schema = SchemaDef(
                id=uuid4(),
                name="docs_test",
                structure_hash="test_hash",
                storage_choice="jsonb",
                status="provisional"
            )
            mock_find_schema.return_value = mock_schema
            mock_process.return_value = [uuid4()]
            
            result = processor.process_documents(
                documents=[{"id": 1, "data": "complex"}],
                request_id="test-request"
            )
            
            assert result["storage_choice"] == "jsonb"
            mock_process.assert_called_once()

    def test_approve_schema_not_found(self, processor, mock_db):
        """Test approving non-existent schema."""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with pytest.raises(JsonProcessingError) as exc_info:
            processor.approve_schema(uuid4(), "reviewer")
        
        assert "not found" in str(exc_info.value).lower()

    def test_approve_schema_not_provisional(self, processor, mock_db):
        """Test approving schema that's not provisional."""
        active_schema = SchemaDef(
            id=uuid4(),
            name="active_table",
            structure_hash="hash",
            storage_choice="sql",
            status="active"
        )
        mock_db.query.return_value.filter.return_value.first.return_value = active_schema
        
        with pytest.raises(JsonProcessingError) as exc_info:
            processor.approve_schema(active_schema.id, "reviewer")
        
        assert "not provisional" in str(exc_info.value).lower()

    def test_reject_schema(self, processor, mock_db):
        """Test rejecting a schema."""
        provisional_schema = SchemaDef(
            id=uuid4(),
            name="provisional_table",
            structure_hash="hash",
            storage_choice="sql",
            status="provisional"
        )
        mock_db.query.return_value.filter.return_value.first.return_value = provisional_schema
        
        with patch.object(processor.db.query, 'filter') as mock_filter:
            mock_filter.return_value.update.return_value = None
            
            result = processor.reject_schema(provisional_schema.id, "reviewer", "Not suitable")
            
            assert result.status == "rejected"
            assert result.reviewed_by == "reviewer"
            assert "Rejection reason" in result.decision_reason

    def test_ddl_execution_failure(self, processor, mock_db):
        """Test DDL execution failure handling."""
        schema_def = SchemaDef(
            id=uuid4(),
            name="test_table",
            structure_hash="hash",
            storage_choice="sql",
            status="provisional",
            ddl="CREATE TABLE test_table (id INT);"
        )
        
        # Mock DDL execution failure
        mock_db.execute.side_effect = Exception("DDL execution failed")
        
        with pytest.raises(JsonProcessingError) as exc_info:
            processor._execute_ddl(schema_def)
        
        assert "Failed to execute DDL" in str(exc_info.value)

    def test_ddl_without_content(self, processor):
        """Test DDL execution with None DDL."""
        schema_def = SchemaDef(
            id=uuid4(),
            name="test_table",
            structure_hash="hash",
            storage_choice="sql",
            status="provisional",
            ddl=None
        )
        
        with pytest.raises(JsonProcessingError) as exc_info:
            processor._execute_ddl(schema_def)
        
        assert "no DDL" in str(exc_info.value).lower()

    def test_process_documents_with_owner(self, processor, mock_db):
        """Test processing documents with owner."""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with patch.object(processor.decider, 'decide') as mock_decide, \
             patch.object(processor, '_find_or_create_schema') as mock_find_schema, \
             patch.object(processor, '_process_sql_documents') as mock_process:
            
            from src.ingest.schema_decider import SchemaDecision
            mock_decision = SchemaDecision(
                storage_choice=StorageChoice.SQL,
                confidence=0.9,
                reason="Test",
                documents_analyzed=1,
                top_level_keys=1,
                max_depth=1,
                field_stability=1.0,
                type_stability=1.0,
                has_array_of_objects=False,
                structure_hash="test_hash",
                fields={}
            )
            mock_decide.return_value = mock_decision
            
            mock_schema = SchemaDef(
                id=uuid4(),
                name="test_table",
                structure_hash="test_hash",
                storage_choice="sql",
                status="provisional"
            )
            mock_find_schema.return_value = mock_schema
            mock_process.return_value = [uuid4()]
            
            result = processor.process_documents(
                documents=[{"id": 1}],
                request_id="test-request",
                owner="user123"
            )
            
            # Verify owner was passed
            mock_process.assert_called_once()
            call_kwargs = mock_process.call_args[1]
            assert call_kwargs["owner"] == "user123"

    def test_collection_name_hint_usage(self, processor, mock_db):
        """Test that collection name hint is used."""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with patch.object(processor.decider, 'decide') as mock_decide, \
             patch.object(processor.decider, 'generate_collection_name') as mock_gen_name, \
             patch.object(processor, '_process_sql_documents'):
            
            from src.ingest.schema_decider import SchemaDecision
            mock_decision = SchemaDecision(
                storage_choice=StorageChoice.SQL,
                confidence=0.9,
                reason="Test",
                documents_analyzed=1,
                top_level_keys=1,
                max_depth=1,
                field_stability=1.0,
                type_stability=1.0,
                has_array_of_objects=False,
                structure_hash="test_hash",
                fields={}
            )
            mock_decide.return_value = mock_decision
            mock_gen_name.return_value = "hinted_table"
            
            processor.process_documents(
                documents=[{"id": 1}],
                request_id="test-request",
                collection_name_hint="My Custom Table"
            )
            
            # Verify hint was passed
            mock_gen_name.assert_called_once()
            assert "My Custom Table" in str(mock_gen_name.call_args)

    def test_lineage_logging(self, processor, mock_db):
        """Test lineage logging for processing stages."""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with patch.object(processor.decider, 'decide') as mock_decide, \
             patch.object(processor, '_find_or_create_schema') as mock_find_schema, \
             patch.object(processor, '_process_sql_documents') as mock_process:
            
            from src.ingest.schema_decider import SchemaDecision
            mock_decision = SchemaDecision(
                storage_choice=StorageChoice.SQL,
                confidence=0.9,
                reason="Test",
                documents_analyzed=1,
                top_level_keys=1,
                max_depth=1,
                field_stability=1.0,
                type_stability=1.0,
                has_array_of_objects=False,
                structure_hash="test_hash",
                fields={}
            )
            mock_decide.return_value = mock_decision
            
            mock_schema = SchemaDef(
                id=uuid4(),
                name="test_table",
                structure_hash="test_hash",
                storage_choice="sql",
                status="provisional"
            )
            mock_find_schema.return_value = mock_schema
            mock_process.return_value = [uuid4()]
            
            processor.process_documents(
                documents=[{"id": 1}],
                request_id="test-request"
            )
            
            # Verify lineage was logged (multiple calls to db.add)
            assert mock_db.add.call_count >= 2  # At least schema and lineage entries

    def test_error_handling_in_processing(self, processor, mock_db):
        """Test error handling during processing."""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with patch.object(processor.decider, 'decide') as mock_decide:
            mock_decide.side_effect = Exception("Analysis failed")
            
            with pytest.raises(JsonProcessingError) as exc_info:
                processor.process_documents(
                    documents=[{"id": 1}],
                    request_id="test-request"
                )
            
            assert "Failed to process" in str(exc_info.value)

    def test_schema_creation_rollback_on_error(self, processor, mock_db):
        """Test that schema creation rolls back on error."""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with patch.object(processor.decider, 'decide') as mock_decide, \
             patch.object(processor.ddl_generator, 'generate_table_ddl') as mock_ddl:
            
            from src.ingest.schema_decider import SchemaDecision
            mock_decision = SchemaDecision(
                storage_choice=StorageChoice.SQL,
                confidence=0.9,
                reason="Test",
                documents_analyzed=1,
                top_level_keys=1,
                max_depth=1,
                field_stability=1.0,
                type_stability=1.0,
                has_array_of_objects=False,
                structure_hash="test_hash",
                fields={}
            )
            mock_decide.return_value = mock_decision
            mock_ddl.return_value = "CREATE TABLE test (id INT);"
            
            # Simulate commit failure
            mock_db.commit.side_effect = Exception("Commit failed")
            
            with pytest.raises(JsonProcessingError):
                processor.process_documents(
                    documents=[{"id": 1}],
                    request_id="test-request"
                )
            
            # Verify rollback was called
            mock_db.rollback.assert_called()

