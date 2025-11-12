"""
Unit tests for schema decision algorithm.
"""

from src.ingest.schema_analyzer import JsonSchemaAnalyzer
from src.ingest.schema_decider import SchemaDecider, StorageChoice


class TestSchemaDecider:
    """Tests for schema decision making."""

    def test_decide_sql_for_stable_schema(self):
        """Test that stable, simple schemas choose SQL."""
        decider = SchemaDecider()

        # Create stable documents
        docs = [
            {"id": 1, "name": "Alice", "age": 30, "active": True},
            {"id": 2, "name": "Bob", "age": 25, "active": False},
            {"id": 3, "name": "Charlie", "age": 35, "active": True},
            {"id": 4, "name": "David", "age": 40, "active": False},
        ]

        decision = decider.decide(docs)

        assert decision.storage_choice == StorageChoice.SQL
        assert decision.confidence > 0.7
        assert decision.top_level_keys <= 4
        assert decision.max_depth <= 1
        assert decision.field_stability > 0.9

    def test_decide_jsonb_for_unstable_schema(self):
        """Test that unstable schemas choose JSONB."""
        decider = SchemaDecider()

        # Create unstable documents (varying fields)
        docs = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "email": "bob@example.com"},
            {"title": "Manager", "department": "Sales"},
            {"id": 123, "code": "XYZ"},
        ]

        decision = decider.decide(docs)

        assert decision.storage_choice == StorageChoice.JSONB
        assert decision.field_stability < 0.6

    def test_decide_jsonb_for_deep_nesting(self):
        """Test that deeply nested schemas choose JSONB."""
        decider = SchemaDecider(max_depth=2)

        docs = [
            {
                "user": {
                    "profile": {
                        "address": {
                            "city": "NYC",
                            "zip": "10001"
                        }
                    }
                }
            }
        ]

        decision = decider.decide(docs)

        assert decision.storage_choice == StorageChoice.JSONB
        assert decision.max_depth > 2

    def test_decide_jsonb_for_many_keys(self):
        """Test that schemas with too many keys choose JSONB."""
        decider = SchemaDecider(max_top_level_keys=10)

        # Create document with many keys
        doc = {f"field{i}": i for i in range(25)}

        decision = decider.decide([doc])

        assert decision.storage_choice == StorageChoice.JSONB
        assert decision.top_level_keys > 10

    def test_decide_jsonb_for_arrays_of_objects(self):
        """Test that arrays of objects choose JSONB."""
        decider = SchemaDecider()

        docs = [
            {
                "user": "Alice",
                "orders": [
                    {"id": 1, "total": 100},
                    {"id": 2, "total": 200}
                ]
            }
        ]

        decision = decider.decide(docs)

        assert decision.storage_choice == StorageChoice.JSONB
        assert decision.has_array_of_objects is True

    def test_decision_includes_rationale(self):
        """Test that decision includes human-readable rationale."""
        decider = SchemaDecider()

        docs = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"}
        ]

        decision = decider.decide(docs)

        assert decision.reason is not None
        assert len(decision.reason) > 0
        assert isinstance(decision.reason, str)

    def test_decision_to_dict(self):
        """Test that decision can be serialized to dict."""
        decider = SchemaDecider()
        docs = [{"id": 1, "name": "Test"}]

        decision = decider.decide(docs)
        result = decision.to_dict()

        assert isinstance(result, dict)
        assert "storage_choice" in result
        assert "confidence" in result
        assert "metadata" in result
        assert "fields" in result

    def test_generate_collection_name_with_hint(self):
        """Test collection name generation with hint."""
        decider = SchemaDecider()
        docs = [{"id": 1}]
        decision = decider.decide(docs)

        name = decider.generate_collection_name(decision, hint="My Users")

        assert name == "my_users"
        assert " " not in name
        assert name.islower()

    def test_generate_collection_name_without_hint(self):
        """Test collection name generation without hint."""
        decider = SchemaDecider()
        docs = [{"id": 1}]
        decision = decider.decide(docs)

        name = decider.generate_collection_name(decision)

        assert len(name) > 0
        if decision.storage_choice == StorageChoice.SQL:
            assert name.startswith("table_")
        else:
            assert name.startswith("docs_")
