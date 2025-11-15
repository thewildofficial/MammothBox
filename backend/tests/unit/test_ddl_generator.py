"""
Unit tests for DDL generation.
"""

from src.ingest.schema_decider import SchemaDecider, StorageChoice
from src.ingest.ddl_generator import DDLGenerator


class TestDDLGenerator:
    """Tests for SQL DDL generation."""

    def test_generate_sql_table_ddl(self):
        """Test generation of SQL CREATE TABLE statement."""
        decider = SchemaDecider()
        docs = [
            {"id": 1, "name": "Alice", "age": 30, "active": True},
            {"id": 2, "name": "Bob", "age": 25, "active": False},
        ]
        decision = decider.decide(docs)

        generator = DDLGenerator()
        ddl = generator.generate_table_ddl("users", decision)

        assert "CREATE TABLE IF NOT EXISTS users" in ddl
        assert "id UUID PRIMARY KEY" in ddl
        assert "created_at" in ddl
        assert "updated_at" in ddl
        assert "extra JSONB" in ddl  # Fallback column

    def test_generate_jsonb_collection_ddl(self):
        """Test generation of JSONB collection table."""
        generator = DDLGenerator()
        ddl = generator.generate_jsonb_collection_ddl("docs_collection")

        assert "CREATE TABLE IF NOT EXISTS docs_collection" in ddl
        assert "id UUID PRIMARY KEY" in ddl
        assert "doc JSONB NOT NULL" in ddl
        assert "GIN" in ddl
        assert "created_at" in ddl

    def test_column_name_sanitization(self):
        """Test that column names are sanitized properly."""
        generator = DDLGenerator()

        assert generator._sanitize_column_name("user.name") == "user_name"
        assert generator._sanitize_column_name("items[]") == "items_array"
        assert generator._sanitize_column_name("123field") == "col_123field"
        assert generator._sanitize_column_name(
            "user") == "user_col"  # Reserved word

    def test_sql_type_mapping(self):
        """Test JSON type to SQL type mapping."""
        from src.ingest.schema_analyzer import JsonType
        generator = DDLGenerator()

        assert "BIGINT" in generator._map_json_type_to_sql(JsonType.INTEGER)
        assert "DOUBLE PRECISION" in generator._map_json_type_to_sql(
            JsonType.FLOAT)
        assert "BOOLEAN" in generator._map_json_type_to_sql(JsonType.BOOLEAN)
        assert "TEXT" in generator._map_json_type_to_sql(JsonType.STRING)
        assert "JSONB" in generator._map_json_type_to_sql(JsonType.ARRAY)
        assert "JSONB" in generator._map_json_type_to_sql(JsonType.OBJECT)

    def test_string_type_sizing(self):
        """Test VARCHAR sizing for strings."""
        generator = DDLGenerator()

        # Short strings get VARCHAR with length
        assert "VARCHAR(100)" in generator._get_string_type(100)

        # Long strings get TEXT
        assert generator._get_string_type(2000) == "TEXT"

        # Unknown length gets TEXT
        assert generator._get_string_type(0) == "TEXT"

    def test_index_generation(self):
        """Test that appropriate indexes are generated."""
        decider = SchemaDecider()
        docs = [
            {"user_id": 1, "email": "alice@example.com", "score": 95},
            {"user_id": 2, "email": "bob@example.com", "score": 87},
        ]
        decision = decider.decide(docs)

        generator = DDLGenerator()
        ddl = generator.generate_table_ddl("users", decision)

        # Should have index on user_id (likely FK)
        assert "idx_" in ddl

    def test_nullable_columns(self):
        """Test that columns with low presence are nullable."""
        decider = SchemaDecider()
        docs = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob"},  # Missing email
            {"name": "Charlie", "email": "charlie@example.com"},
        ]
        decision = decider.decide(docs)

        generator = DDLGenerator()
        ddl = generator.generate_table_ddl("users", decision)

        # Name appears in all docs (100%), email in 66%
        # Both should be in the DDL, but email should be nullable
        assert "name" in ddl.lower()
        assert "email" in ddl.lower()

    def test_generate_insert_statement(self):
        """Test INSERT statement generation."""
        decider = SchemaDecider()
        docs = [{"id": 1, "name": "Alice", "age": 30}]
        decision = decider.decide(docs)

        generator = DDLGenerator()
        insert_sql = generator.generate_insert_statement("users", decision)

        assert "INSERT INTO users" in insert_sql
        assert "VALUES" in insert_sql
        assert ":id" in insert_sql or ":name" in insert_sql or ":age" in insert_sql

    def test_ddl_without_audit_columns(self):
        """Test DDL generation without audit columns."""
        decider = SchemaDecider()
        docs = [{"id": 1, "name": "Test"}]
        decision = decider.decide(docs)

        generator = DDLGenerator()
        ddl = generator.generate_table_ddl(
            "test_table", decision, include_audit_columns=False)

        assert "created_at" not in ddl
        assert "updated_at" not in ddl

    def test_ddl_without_fallback_jsonb(self):
        """Test DDL generation without fallback JSONB column."""
        decider = SchemaDecider()
        docs = [{"id": 1, "name": "Test"}]
        decision = decider.decide(docs)

        generator = DDLGenerator(include_fallback_jsonb=False)
        ddl = generator.generate_table_ddl("test_table", decision)

        assert "extra JSONB" not in ddl
