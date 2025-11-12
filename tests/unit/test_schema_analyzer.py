"""
Unit tests for JSON schema analysis and flattening.
"""

import pytest
from src.ingest.schema_analyzer import (
    JsonSchemaAnalyzer,
    JsonType,
    flatten_json,
    detect_json_type
)


class TestJsonTypeDetection:
    """Tests for JSON type detection."""

    def test_detect_null(self):
        assert detect_json_type(None) == JsonType.NULL

    def test_detect_boolean(self):
        assert detect_json_type(True) == JsonType.BOOLEAN
        assert detect_json_type(False) == JsonType.BOOLEAN

    def test_detect_integer(self):
        assert detect_json_type(42) == JsonType.INTEGER
        assert detect_json_type(0) == JsonType.INTEGER
        assert detect_json_type(-100) == JsonType.INTEGER

    def test_detect_float(self):
        assert detect_json_type(3.14) == JsonType.FLOAT
        assert detect_json_type(-0.5) == JsonType.FLOAT

    def test_detect_string(self):
        assert detect_json_type("hello") == JsonType.STRING
        assert detect_json_type("") == JsonType.STRING

    def test_detect_array(self):
        assert detect_json_type([1, 2, 3]) == JsonType.ARRAY
        assert detect_json_type([]) == JsonType.ARRAY

    def test_detect_object(self):
        assert detect_json_type({"key": "value"}) == JsonType.OBJECT
        assert detect_json_type({}) == JsonType.OBJECT


class TestJsonFlattening:
    """Tests for JSON flattening."""

    def test_flatten_simple_object(self):
        obj = {"name": "Alice", "age": 30}
        result = flatten_json(obj)

        assert "name" in result
        assert "age" in result
        assert result["name"][0] == "Alice"
        assert result["age"][0] == 30

    def test_flatten_nested_object(self):
        obj = {
            "user": {
                "name": "Bob",
                "address": {
                    "city": "NYC"
                }
            }
        }
        result = flatten_json(obj, max_depth=3)

        assert "user" in result
        assert "user.name" in result
        assert "user.address" in result
        assert "user.address.city" in result

    def test_flatten_with_array(self):
        obj = {
            "tags": ["python", "fastapi"],
            "items": [{"id": 1}, {"id": 2}]
        }
        result = flatten_json(obj)

        assert "tags" in result
        assert "items[]" in result  # Array of objects gets special marker

    def test_flatten_respects_max_depth(self):
        obj = {
            "a": {
                "b": {
                    "c": {
                        "d": "too deep"
                    }
                }
            }
        }
        result = flatten_json(obj, max_depth=2)

        assert "a" in result
        assert "a.b" in result
        # Should not include a.b.c because depth is 3
        assert "a.b.c" not in result


class TestJsonSchemaAnalyzer:
    """Tests for JSON schema analyzer."""

    def test_analyze_single_document(self):
        analyzer = JsonSchemaAnalyzer()
        doc = {"name": "Alice", "age": 30, "active": True}

        analyzer.analyze_document(doc)

        assert analyzer.documents_analyzed == 1
        assert len(analyzer.top_level_keys) == 3
        assert "name" in analyzer.field_stats
        assert "age" in analyzer.field_stats
        assert "active" in analyzer.field_stats

    def test_analyze_batch(self):
        analyzer = JsonSchemaAnalyzer(max_sample_size=5)
        docs = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
            {"name": "Charlie", "age": 35}
        ]

        analyzer.analyze_batch(docs)

        assert analyzer.documents_analyzed == 3
        assert len(analyzer.top_level_keys) == 2

    def test_field_stability_calculation(self):
        analyzer = JsonSchemaAnalyzer()
        docs = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
            {"name": "Charlie"}  # Missing age
        ]

        analyzer.analyze_batch(docs)

        # Name appears in 100% of docs
        name_stats = analyzer.field_stats["name"]
        assert name_stats.get_presence_fraction(3) == 1.0

        # Age appears in 66% of docs
        age_stats = analyzer.field_stats["age"]
        assert abs(age_stats.get_presence_fraction(3) - 0.666) < 0.01

    def test_type_stability(self):
        analyzer = JsonSchemaAnalyzer()
        docs = [
            {"value": 10},
            {"value": 20},
            {"value": "thirty"}  # Different type
        ]

        analyzer.analyze_batch(docs)

        value_stats = analyzer.field_stats["value"]
        dominant_type, type_stability = value_stats.get_dominant_type()

        assert dominant_type == JsonType.INTEGER
        assert abs(type_stability - 0.666) < 0.01

    def test_structure_hash_generation(self):
        analyzer1 = JsonSchemaAnalyzer()
        analyzer1.analyze_batch([
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25}
        ])

        analyzer2 = JsonSchemaAnalyzer()
        analyzer2.analyze_batch([
            {"name": "Charlie", "age": 35},
            {"name": "David", "age": 40}
        ])

        # Same structure should produce same hash
        assert analyzer1.get_structure_hash() == analyzer2.get_structure_hash()

    def test_detect_array_of_objects(self):
        analyzer = JsonSchemaAnalyzer()
        doc = {
            "items": [
                {"id": 1, "name": "Item1"},
                {"id": 2, "name": "Item2"}
            ]
        }

        analyzer.analyze_document(doc)

        assert analyzer.has_array_of_objects() is True

    def test_max_depth_tracking(self):
        analyzer = JsonSchemaAnalyzer(max_depth=5)
        doc = {
            "a": {
                "b": {
                    "c": {
                        "d": "deep"
                    }
                }
            }
        }

        analyzer.analyze_document(doc)

        assert analyzer.max_observed_depth == 4
