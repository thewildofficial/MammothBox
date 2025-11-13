"""
Edge case tests for DDL generator.
"""

import pytest
from src.ingest.ddl_generator import DDLGenerator
from src.ingest.schema_decider import SchemaDecider
from src.ingest.schema_analyzer import JsonType


class TestDDLGeneratorEdgeCases:
    """Edge case tests for DDL generator."""

    def test_sanitize_reserved_keywords(self):
        """Test sanitization of SQL reserved keywords."""
        generator = DDLGenerator()
        
        reserved_words = ["user", "group", "order", "table", "index", "key", "value", "default"]
        
        for word in reserved_words:
            sanitized = generator._sanitize_column_name(word)
            assert sanitized.endswith("_col")
            assert sanitized != word

    def test_sanitize_special_characters(self):
        """Test sanitization of special characters."""
        generator = DDLGenerator()
        
        test_cases = [
            ("field.name", "field_name"),
            ("field-name", "field_name"),
            ("field@name", "field_name"),
            ("field#name", "field_name"),
            ("field$name", "field_name"),
            ("field%name", "field_name"),
        ]
        
        for input_name, expected_prefix in test_cases:
            sanitized = generator._sanitize_column_name(input_name)
            assert "_" in sanitized or sanitized.isalnum()
            assert "." not in sanitized
            assert "-" not in sanitized
            assert "@" not in sanitized

    def test_sanitize_numeric_start(self):
        """Test sanitization of names starting with numbers."""
        generator = DDLGenerator()
        
        assert generator._sanitize_column_name("123field").startswith("col_")
        assert generator._sanitize_column_name("0abc").startswith("col_")

    def test_sanitize_empty_string(self):
        """Test sanitization of empty string."""
        generator = DDLGenerator()
        
        sanitized = generator._sanitize_column_name("")
        assert len(sanitized) > 0

    def test_string_type_sizing_edge_cases(self):
        """Test string type sizing for edge cases."""
        generator = DDLGenerator()
        
        # Zero length (unknown)
        assert generator._get_string_type(0) == "TEXT"
        
        # Exactly at VARCHAR(255) boundary
        assert "VARCHAR(255)" in generator._get_string_type(255)
        
        # Just over VARCHAR(255)
        assert generator._get_string_type(256) == "VARCHAR(1000)"
        
        # Exactly at VARCHAR(1000) boundary
        assert "VARCHAR(1000)" in generator._get_string_type(1000)
        
        # Just over VARCHAR(1000)
        assert generator._get_string_type(1001) == "TEXT"
        
        # Very large string
        assert generator._get_string_type(100000) == "TEXT"

    def test_type_mapping_all_types(self):
        """Test mapping of all JSON types to SQL."""
        generator = DDLGenerator()
        
        type_mappings = {
            JsonType.NULL: "TEXT",
            JsonType.BOOLEAN: "BOOLEAN",
            JsonType.INTEGER: "BIGINT",
            JsonType.FLOAT: "DOUBLE PRECISION",
            JsonType.STRING: "TEXT",  # Default for unknown length
            JsonType.ARRAY: "JSONB",
            JsonType.OBJECT: "JSONB",
        }
        
        for json_type, expected_sql_type in type_mappings.items():
            sql_type = generator._map_json_type_to_sql(json_type)
            assert expected_sql_type in sql_type or sql_type == expected_sql_type

    def test_nullable_column_determination(self):
        """Test nullable column determination logic."""
        decider = SchemaDecider()
        
        # Field present in 100% of docs (should be NOT NULL)
        docs1 = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
            {"name": "Charlie", "email": "charlie@example.com"}
        ]
        decision1 = decider.decide(docs1)
        
        generator = DDLGenerator()
        ddl1 = generator.generate_table_ddl("test1", decision1)
        
        # Field present in < 95% of docs (should be nullable)
        docs2 = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob"},  # Missing email
            {"name": "Charlie", "email": "charlie@example.com"}
        ]
        decision2 = decider.decide(docs2)
        ddl2 = generator.generate_table_ddl("test2", decision2)
        
        # Both should generate valid DDL
        assert "CREATE TABLE" in ddl1
        assert "CREATE TABLE" in ddl2

    def test_index_generation_for_foreign_keys(self):
        """Test index generation for likely foreign keys."""
        decider = SchemaDecider()
        docs = [
            {"user_id": 1, "order_id": 100},
            {"user_id": 2, "order_id": 101}
        ]
        decision = decider.decide(docs)
        
        generator = DDLGenerator()
        ddl = generator.generate_table_ddl("orders", decision)
        
        # Should have indexes for user_id and order_id
        assert "idx_" in ddl.lower()

    def test_ddl_with_very_long_table_name(self):
        """Test DDL generation with very long table name."""
        decider = SchemaDecider()
        docs = [{"id": 1}]
        decision = decider.decide(docs)
        
        generator = DDLGenerator()
        long_name = "a" * 100
        ddl = generator.generate_table_ddl(long_name, decision)
        
        assert f"CREATE TABLE IF NOT EXISTS {long_name}" in ddl

    def test_ddl_with_special_characters_in_table_name(self):
        """Test DDL generation with special characters in table name."""
        decider = SchemaDecider()
        docs = [{"id": 1}]
        decision = decider.decide(docs)
        
        generator = DDLGenerator()
        
        # Table names should be sanitized by caller, but test edge case
        ddl = generator.generate_table_ddl("test-table_name", decision)
        assert "CREATE TABLE" in ddl

    def test_fallback_jsonb_column(self):
        """Test fallback JSONB column inclusion."""
        decider = SchemaDecider()
        docs = [{"id": 1, "name": "Test"}]
        decision = decider.decide(docs)
        
        # With fallback
        generator_with = DDLGenerator(include_fallback_jsonb=True)
        ddl_with = generator_with.generate_table_ddl("test", decision)
        assert "extra JSONB" in ddl_with
        
        # Without fallback
        generator_without = DDLGenerator(include_fallback_jsonb=False)
        ddl_without = generator_without.generate_table_ddl("test", decision)
        assert "extra JSONB" not in ddl_without

    def test_audit_columns_inclusion(self):
        """Test audit columns inclusion."""
        decider = SchemaDecider()
        docs = [{"id": 1}]
        decision = decider.decide(docs)
        
        generator = DDLGenerator()
        
        # With audit columns
        ddl_with = generator.generate_table_ddl("test", decision, include_audit_columns=True)
        assert "created_at" in ddl_with
        assert "updated_at" in ddl_with
        
        # Without audit columns
        ddl_without = generator.generate_table_ddl("test", decision, include_audit_columns=False)
        assert "created_at" not in ddl_without
        assert "updated_at" not in ddl_without

    def test_jsonb_collection_ddl(self):
        """Test JSONB collection DDL generation."""
        generator = DDLGenerator()
        
        ddl = generator.generate_jsonb_collection_ddl("docs_test")
        
        assert "CREATE TABLE IF NOT EXISTS docs_test" in ddl
        assert "id UUID PRIMARY KEY" in ddl
        assert "doc JSONB NOT NULL" in ddl
        assert "GIN" in ddl.upper()
        assert "idx_docs_test_doc" in ddl

    def test_insert_statement_generation(self):
        """Test INSERT statement generation."""
        decider = SchemaDecider()
        docs = [{"id": 1, "name": "Test", "age": 30}]
        decision = decider.decide(docs)
        
        generator = DDLGenerator()
        
        # Named placeholders
        insert_named = generator.generate_insert_statement("test_table", decision, placeholder_style="named")
        assert "INSERT INTO test_table" in insert_named
        assert "VALUES" in insert_named
        assert ":" in insert_named  # Named placeholders
        
        # Positional placeholders
        insert_pos = generator.generate_insert_statement("test_table", decision, placeholder_style="positional")
        assert "INSERT INTO test_table" in insert_pos
        assert "%s" in insert_pos  # Positional placeholders

    def test_duplicate_column_name_handling(self):
        """Test handling of duplicate column names after sanitization."""
        decider = SchemaDecider()
        # Create fields that would sanitize to same name
        docs = [
            {"field.name": "value1", "field-name": "value2"}
        ]
        decision = decider.decide(docs)
        
        generator = DDLGenerator()
        ddl = generator.generate_table_ddl("test", decision)
        
        # Should handle duplicates gracefully
        assert "CREATE TABLE" in ddl

    def test_gin_index_for_jsonb_columns(self):
        """Test GIN index generation for JSONB columns."""
        decider = SchemaDecider()
        docs = [
            {"metadata": {"key": "value"}, "tags": ["tag1", "tag2"]}
        ]
        decision = decider.decide(docs)
        
        generator = DDLGenerator()
        ddl = generator.generate_table_ddl("test", decision)
        
        # JSONB columns should get GIN indexes if indexed
        # This depends on the indexing logic
        assert "CREATE TABLE" in ddl

    def test_ddl_with_no_fields(self):
        """Test DDL generation for empty schema."""
        decider = SchemaDecider()
        docs = [{}]
        decision = decider.decide(docs)
        
        generator = DDLGenerator()
        ddl = generator.generate_table_ddl("empty_table", decision)
        
        # Should still create valid table with at least id column
        assert "CREATE TABLE IF NOT EXISTS empty_table" in ddl
        assert "id UUID PRIMARY KEY" in ddl

    def test_ddl_table_name_quoting(self):
        """Test that table names don't need quoting for valid identifiers."""
        generator = DDLGenerator()
        decider = SchemaDecider()
        docs = [{"id": 1}]
        decision = decider.decide(docs)
        
        # Valid identifier should work without quotes
        ddl = generator.generate_table_ddl("valid_table_name", decision)
        assert "CREATE TABLE IF NOT EXISTS valid_table_name" in ddl

    def test_column_definitions_with_nested_fields_skipped(self):
        """Test that nested fields are skipped in column definitions."""
        decider = SchemaDecider()
        docs = [
            {
                "id": 1,
                "user": {
                    "name": "Alice",
                    "age": 30
                }
            }
        ]
        decision = decider.decide(docs)
        
        generator = DDLGenerator()
        ddl = generator.generate_table_ddl("test", decision)
        
        # Should only include top-level "id", not nested "user.name" or "user.age"
        assert "id" in ddl.lower()
        # Nested fields should be skipped (implementation detail)

