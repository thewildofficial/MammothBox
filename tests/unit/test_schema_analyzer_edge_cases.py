"""
Edge case tests for JSON schema analyzer.
"""

import pytest
from src.ingest.schema_analyzer import (
    JsonSchemaAnalyzer,
    JsonType,
    flatten_json,
    detect_json_type,
    FieldStats
)


class TestSchemaAnalyzerEdgeCases:
    """Edge case tests for schema analyzer."""

    def test_empty_document(self):
        """Test handling of empty document."""
        analyzer = JsonSchemaAnalyzer()
        analyzer.analyze_document({})
        
        assert analyzer.documents_analyzed == 1
        assert len(analyzer.top_level_keys) == 0
        assert len(analyzer.field_stats) == 0
        assert analyzer.get_field_stability() == 0.0
        assert analyzer.get_type_stability() == 0.0

    def test_empty_document_list(self):
        """Test handling of empty document list."""
        analyzer = JsonSchemaAnalyzer()
        analyzer.analyze_batch([])
        
        assert analyzer.documents_analyzed == 0
        assert len(analyzer.top_level_keys) == 0
        assert len(analyzer.field_stats) == 0

    def test_single_field_document(self):
        """Test document with only one field."""
        analyzer = JsonSchemaAnalyzer()
        analyzer.analyze_document({"id": 1})
        
        assert analyzer.documents_analyzed == 1
        assert len(analyzer.top_level_keys) == 1
        assert "id" in analyzer.field_stats
        assert analyzer.field_stats["id"].get_dominant_type()[0] == JsonType.INTEGER

    def test_all_null_values(self):
        """Test document where all values are null."""
        analyzer = JsonSchemaAnalyzer()
        docs = [
            {"name": None, "age": None},
            {"name": None, "age": None}
        ]
        analyzer.analyze_batch(docs)
        
        name_stats = analyzer.field_stats["name"]
        assert name_stats.get_dominant_type()[0] == JsonType.NULL
        assert name_stats.null_count == 2

    def test_mixed_types_in_same_field(self):
        """Test field that has different types across documents."""
        analyzer = JsonSchemaAnalyzer()
        docs = [
            {"value": 42},
            {"value": "forty-two"},
            {"value": True},
            {"value": None},
            {"value": 3.14}
        ]
        analyzer.analyze_batch(docs)
        
        value_stats = analyzer.field_stats["value"]
        dominant_type, stability = value_stats.get_dominant_type()
        # Should detect most common type
        assert stability < 1.0  # Not perfectly stable

    def test_very_deep_nesting(self):
        """Test extremely nested structures."""
        analyzer = JsonSchemaAnalyzer(max_depth=10)
        
        # Create 10 levels deep nesting
        doc = {"level1": {}}
        current = doc["level1"]
        for i in range(2, 11):
            current[f"level{i}"] = {}
            current = current[f"level{i}"]
        current["value"] = "deep"
        
        analyzer.analyze_document(doc)
        assert analyzer.max_observed_depth == 10

    def test_large_array_of_primitives(self):
        """Test large array of primitive values."""
        analyzer = JsonSchemaAnalyzer()
        doc = {
            "numbers": list(range(1000)),
            "strings": [f"item_{i}" for i in range(100)]
        }
        
        analyzer.analyze_document(doc)
        assert "numbers" in analyzer.field_stats
        assert "strings" in analyzer.field_stats
        assert analyzer.field_stats["numbers"].get_dominant_type()[0] == JsonType.ARRAY

    def test_unicode_and_special_characters(self):
        """Test handling of Unicode and special characters."""
        analyzer = JsonSchemaAnalyzer()
        docs = [
            {"name": "José", "emoji": "😀", "chinese": "中文"},
            {"name": "François", "emoji": "🎉", "chinese": "测试"}
        ]
        
        analyzer.analyze_batch(docs)
        assert "name" in analyzer.field_stats
        assert "emoji" in analyzer.field_stats
        assert "chinese" in analyzer.field_stats
        
        # Check that Unicode strings are handled correctly
        name_stats = analyzer.field_stats["name"]
        assert name_stats.get_dominant_type()[0] == JsonType.STRING

    def test_field_names_with_special_characters(self):
        """Test field names with dots, dashes, and special chars."""
        analyzer = JsonSchemaAnalyzer()
        doc = {
            "field.with.dots": "value1",
            "field-with-dashes": "value2",
            "field_with_underscores": "value3",
            "123numeric": "value4",
            "field@special": "value5"
        }
        
        analyzer.analyze_document(doc)
        # All fields should be tracked
        assert len(analyzer.field_stats) >= 5

    def test_very_long_string_values(self):
        """Test handling of very long string values."""
        analyzer = JsonSchemaAnalyzer()
        long_string = "x" * 10000
        doc = {"description": long_string}
        
        analyzer.analyze_document(doc)
        stats = analyzer.field_stats["description"]
        assert stats.max_value_length == 10000
        assert stats.get_dominant_type()[0] == JsonType.STRING

    def test_array_with_mixed_types(self):
        """Test array containing different types."""
        analyzer = JsonSchemaAnalyzer()
        doc = {
            "mixed_array": [1, "two", 3.0, True, None, {"nested": "object"}]
        }
        
        analyzer.analyze_document(doc)
        assert "mixed_array" in analyzer.field_stats
        assert analyzer.field_stats["mixed_array"].get_dominant_type()[0] == JsonType.ARRAY

    def test_nested_arrays(self):
        """Test nested arrays."""
        analyzer = JsonSchemaAnalyzer()
        doc = {
            "matrix": [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
        }
        
        analyzer.analyze_document(doc)
        assert "matrix" in analyzer.field_stats

    def test_empty_arrays(self):
        """Test empty arrays."""
        analyzer = JsonSchemaAnalyzer()
        docs = [
            {"items": []},
            {"items": [1, 2, 3]},
            {"items": []}
        ]
        
        analyzer.analyze_batch(docs)
        assert "items" in analyzer.field_stats
        assert analyzer.field_stats["items"].get_dominant_type()[0] == JsonType.ARRAY

    def test_sample_size_limiting(self):
        """Test that sample size limit is respected."""
        analyzer = JsonSchemaAnalyzer(max_sample_size=5)
        docs = [{"id": i} for i in range(100)]
        
        analyzer.analyze_batch(docs)
        assert analyzer.documents_analyzed == 5

    def test_structure_hash_consistency(self):
        """Test that structure hash is consistent for same structure."""
        analyzer1 = JsonSchemaAnalyzer()
        analyzer2 = JsonSchemaAnalyzer()
        
        docs1 = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        docs2 = [{"a": 5, "b": 6}, {"a": 7, "b": 8}]
        
        analyzer1.analyze_batch(docs1)
        analyzer2.analyze_batch(docs2)
        
        # Same structure, different values should produce same hash
        assert analyzer1.get_structure_hash() == analyzer2.get_structure_hash()

    def test_structure_hash_different_structures(self):
        """Test that different structures produce different hashes."""
        analyzer1 = JsonSchemaAnalyzer()
        analyzer2 = JsonSchemaAnalyzer()
        
        docs1 = [{"a": 1, "b": 2}]
        docs2 = [{"x": 1, "y": 2}]
        
        analyzer1.analyze_batch(docs1)
        analyzer2.analyze_batch(docs2)
        
        assert analyzer1.get_structure_hash() != analyzer2.get_structure_hash()

    def test_field_stats_presence_fraction_edge_cases(self):
        """Test presence fraction calculation edge cases."""
        stats = FieldStats("test_field")
        
        # Test with zero total docs
        assert stats.get_presence_fraction(0) == 0.0
        
        # Test with presence
        stats.add_value("value", JsonType.STRING)
        assert stats.get_presence_fraction(1) == 1.0
        assert stats.get_presence_fraction(2) == 0.5

    def test_foreign_key_detection(self):
        """Test foreign key detection heuristics."""
        analyzer = JsonSchemaAnalyzer()
        docs = [
            {"user_id": 1, "order_id": 100, "product_key": "ABC123"},
            {"user_id": 2, "order_id": 101, "product_key": "DEF456"}
        ]
        
        analyzer.analyze_batch(docs)
        
        user_id_stats = analyzer.field_stats["user_id"]
        order_id_stats = analyzer.field_stats["order_id"]
        product_key_stats = analyzer.field_stats["product_key"]
        
        assert user_id_stats.is_likely_foreign_key()
        assert order_id_stats.is_likely_foreign_key()
        assert product_key_stats.is_likely_foreign_key()

    def test_flatten_empty_object(self):
        """Test flattening empty object."""
        result = flatten_json({})
        assert len(result) == 0

    def test_flatten_with_none_values(self):
        """Test flattening with None values."""
        obj = {"name": None, "age": 30}
        result = flatten_json(obj)
        
        assert "name" in result
        assert result["name"][1] == JsonType.NULL

    def test_flatten_array_of_objects_detection(self):
        """Test detection of array of objects."""
        obj = {
            "users": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"}
            ]
        }
        result = flatten_json(obj)
        
        assert "users[]" in result

    def test_flatten_array_of_primitives(self):
        """Test flattening array of primitives (not objects)."""
        obj = {
            "tags": ["python", "fastapi"],
            "numbers": [1, 2, 3]
        }
        result = flatten_json(obj)
        
        assert "tags" in result
        assert "numbers" in result
        # Arrays of primitives don't get [] marker
        assert "tags[]" not in result
        assert "numbers[]" not in result

    def test_max_depth_enforcement(self):
        """Test that max_depth is strictly enforced."""
        obj = {
            "a": {
                "b": {
                    "c": {
                        "d": "value"
                    }
                }
            }
        }
        
        result = flatten_json(obj, max_depth=2)
        
        assert "a" in result
        assert "a.b" in result
        assert "a.b.c" not in result  # Should be cut off at depth 2

