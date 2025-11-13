"""
Edge case tests for schema decider.
"""

import pytest
from src.ingest.schema_decider import SchemaDecider, StorageChoice, SchemaDecision


class TestSchemaDeciderEdgeCases:
    """Edge case tests for schema decider."""

    def test_empty_document_list(self):
        """Test handling of empty document list."""
        decider = SchemaDecider()
        
        # Empty list should still produce a decision (though with no fields)
        decision = decider.decide([])
        assert isinstance(decision, SchemaDecision)
        assert decision.documents_analyzed == 0

    def test_single_document(self):
        """Test decision with single document."""
        decider = SchemaDecider()
        docs = [{"id": 1, "name": "Test"}]
        
        decision = decider.decide(docs)
        
        assert isinstance(decision, SchemaDecision)
        assert decision.documents_analyzed == 1
        assert decision.storage_choice in [StorageChoice.SQL, StorageChoice.JSONB]

    def test_at_threshold_boundary_top_level_keys(self):
        """Test decision at threshold boundary for top-level keys."""
        # Test exactly at threshold (20 keys)
        decider = SchemaDecider(max_top_level_keys=20)
        doc = {f"field{i}": i for i in range(20)}
        
        decision = decider.decide([doc])
        # Should still prefer SQL if other criteria are met
        assert decision.top_level_keys == 20

    def test_just_over_threshold_top_level_keys(self):
        """Test decision just over threshold for top-level keys."""
        decider = SchemaDecider(max_top_level_keys=20)
        doc = {f"field{i}": i for i in range(21)}  # One over threshold
        
        decision = decider.decide([doc])
        # Should trigger hard veto for JSONB
        assert decision.storage_choice == StorageChoice.JSONB
        assert decision.top_level_keys == 21

    def test_at_threshold_boundary_depth(self):
        """Test decision at threshold boundary for depth."""
        decider = SchemaDecider(max_depth=2)
        doc = {
            "level1": {
                "level2": "value"
            }
        }
        
        decision = decider.decide([doc])
        assert decision.max_depth == 2

    def test_just_over_threshold_depth(self):
        """Test decision just over threshold for depth."""
        decider = SchemaDecider(max_depth=2)
        doc = {
            "level1": {
                "level2": {
                    "level3": "value"
                }
            }
        }
        
        decision = decider.decide([doc])
        # Should trigger hard veto for JSONB
        assert decision.storage_choice == StorageChoice.JSONB
        assert decision.max_depth > 2

    def test_at_threshold_boundary_stability(self):
        """Test decision at threshold boundary for field stability."""
        decider = SchemaDecider(stability_threshold=0.6)
        
        # Create docs with exactly 60% field stability
        docs = [
            {"field1": 1, "field2": 2, "field3": 3},
            {"field1": 4, "field2": 5, "field3": 6},
            {"field1": 7, "field2": 8},  # Missing field3
            {"field1": 9, "field2": 10, "field3": 11},
            {"field1": 12, "field2": 13}  # Missing field3
        ]
        
        decision = decider.decide(docs)
        # Should meet threshold (field3 appears in 60% = 3/5)
        assert decision.field_stability >= 0.6

    def test_just_below_threshold_stability(self):
        """Test decision just below threshold for field stability."""
        decider = SchemaDecider(stability_threshold=0.6)
        
        # Create docs with < 60% field stability
        docs = [
            {"field1": 1, "field2": 2},
            {"field1": 3, "field2": 4},
            {"field1": 5},  # Missing field2
            {"field1": 6},  # Missing field2
        ]
        
        decision = decider.decide(docs)
        # field2 appears in 50% (2/4), below threshold
        assert decision.field_stability < 0.6

    def test_sql_score_calculation_edge_cases(self):
        """Test SQL score calculation at boundaries."""
        decider = SchemaDecider()
        
        # Perfect SQL candidate (should score 1.0)
        perfect_docs = [
            {"id": i, "name": f"User{i}", "age": 20+i, "active": True}
            for i in range(10)
        ]
        
        decision = decider.decide(perfect_docs)
        # Should have high SQL score if chosen
        if decision.storage_choice == StorageChoice.SQL:
            assert decision.confidence >= 0.85

    def test_confidence_score_range(self):
        """Test that confidence scores are in valid range."""
        decider = SchemaDecider()
        docs = [{"id": 1, "name": "Test"}]
        
        decision = decider.decide(docs)
        
        assert 0.0 <= decision.confidence <= 1.0

    def test_decision_reason_not_empty(self):
        """Test that decision reason is always provided."""
        decider = SchemaDecider()
        docs = [{"id": 1}]
        
        decision = decider.decide(docs)
        
        assert decision.reason is not None
        assert len(decision.reason) > 0
        assert isinstance(decision.reason, str)

    def test_collection_name_sanitization_edge_cases(self):
        """Test collection name generation with edge cases."""
        decider = SchemaDecider()
        docs = [{"id": 1}]
        decision = decider.decide(docs)
        
        # Test with special characters
        name1 = decider.generate_collection_name(decision, hint="My-Collection Name!")
        assert " " not in name1
        assert "-" not in name1
        assert "!" not in name1
        
        # Test with numbers at start
        name2 = decider.generate_collection_name(decision, hint="123collection")
        assert name2.startswith("col_") or name2.startswith("table_") or name2.startswith("docs_")
        
        # Test with empty hint
        name3 = decider.generate_collection_name(decision, hint="")
        assert len(name3) > 0

    def test_mixed_stability_scenario(self):
        """Test documents with mixed stability patterns."""
        decider = SchemaDecider()
        
        # Some fields stable, some unstable
        docs = [
            {"id": 1, "name": "Alice", "optional": "value1"},
            {"id": 2, "name": "Bob", "optional": "value2"},
            {"id": 3, "name": "Charlie"},  # Missing optional
            {"id": 4, "name": "David", "optional": "value3"},
            {"id": 5, "name": "Eve"}  # Missing optional
        ]
        
        decision = decider.decide(docs)
        
        # id and name should be stable (100%), optional less so (60%)
        assert decision.field_stability > 0.0
        assert decision.top_level_keys == 3

    def test_array_of_objects_hard_veto(self):
        """Test that array of objects always triggers JSONB."""
        decider = SchemaDecider()
        
        # Even with perfect stability, arrays of objects should veto SQL
        docs = [
            {
                "id": 1,
                "name": "User1",
                "orders": [{"order_id": 1}, {"order_id": 2}]
            },
            {
                "id": 2,
                "name": "User2",
                "orders": [{"order_id": 3}]
            }
        ]
        
        decision = decider.decide(docs)
        
        # Should be JSONB due to array of objects
        assert decision.storage_choice == StorageChoice.JSONB
        assert decision.has_array_of_objects is True
        assert decision.confidence >= 0.95  # High confidence for hard veto

    def test_multiple_hard_vetos(self):
        """Test document that triggers multiple hard vetos."""
        decider = SchemaDecider(max_top_level_keys=20, max_depth=2)
        
        # Document with many keys, deep nesting, AND arrays of objects
        doc = {
            **{f"field{i}": i for i in range(25)},  # Too many keys
            "deep": {
                "nested": {
                    "very": {
                        "deep": "value"  # Too deep
                    }
                }
            },
            "items": [{"id": 1}, {"id": 2}]  # Array of objects
        }
        
        decision = decider.decide([doc])
        
        # Should be JSONB with high confidence
        assert decision.storage_choice == StorageChoice.JSONB
        assert decision.confidence >= 0.90

    def test_type_stability_edge_cases(self):
        """Test type stability calculation edge cases."""
        decider = SchemaDecider()
        
        # All same type
        docs1 = [{"value": i} for i in range(10)]
        decision1 = decider.decide(docs1)
        assert decision1.type_stability == 1.0
        
        # Mixed types
        docs2 = [
            {"value": 1},
            {"value": "two"},
            {"value": 3.0},
            {"value": True}
        ]
        decision2 = decider.decide(docs2)
        assert decision2.type_stability < 1.0

    def test_decision_metadata_completeness(self):
        """Test that decision metadata is complete."""
        decider = SchemaDecider()
        docs = [{"id": 1, "name": "Test"}]
        
        decision = decider.decide(docs)
        
        # Check all required fields
        assert hasattr(decision, 'storage_choice')
        assert hasattr(decision, 'confidence')
        assert hasattr(decision, 'reason')
        assert hasattr(decision, 'documents_analyzed')
        assert hasattr(decision, 'top_level_keys')
        assert hasattr(decision, 'max_depth')
        assert hasattr(decision, 'field_stability')
        assert hasattr(decision, 'type_stability')
        assert hasattr(decision, 'has_array_of_objects')
        assert hasattr(decision, 'structure_hash')
        assert hasattr(decision, 'fields')

    def test_to_dict_serialization(self):
        """Test that decision can be serialized to dict."""
        decider = SchemaDecider()
        docs = [{"id": 1, "name": "Test"}]
        
        decision = decider.decide(docs)
        result = decision.to_dict()
        
        assert isinstance(result, dict)
        assert "storage_choice" in result
        assert "confidence" in result
        assert "reason" in result
        assert "metadata" in result
        assert "fields" in result
        
        # Check metadata structure
        metadata = result["metadata"]
        assert "documents_analyzed" in metadata
        assert "top_level_keys" in metadata
        assert "max_depth" in metadata

    def test_explain_decision_format(self):
        """Test that explain_decision produces readable output."""
        decider = SchemaDecider()
        docs = [{"id": 1, "name": "Test"}]
        
        decision = decider.decide(docs)
        explanation = decider.explain_decision(decision)
        
        assert isinstance(explanation, str)
        assert len(explanation) > 0
        assert "SCHEMA DECISION ANALYSIS" in explanation
        assert "Storage Choice" in explanation
        assert "Confidence" in explanation

