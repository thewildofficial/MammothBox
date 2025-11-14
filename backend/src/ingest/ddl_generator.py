"""DDL Generator for SQL schemas."""

from typing import List, Dict, Any, Set
from src.ingest.schema_analyzer import JsonType, FieldStats
from src.ingest.schema_decider import SchemaDecision


class DDLGenerator:
    """Generates SQL DDL statements from analyzed JSON documents."""

    def __init__(self, include_fallback_jsonb: bool = True):
        self.include_fallback_jsonb = include_fallback_jsonb

    def _map_json_type_to_sql(
        self,
        json_type: JsonType,
        max_length: int = 0,
        is_nullable: bool = True
    ) -> str:
        type_mapping = {
            JsonType.NULL: "TEXT",
            JsonType.BOOLEAN: "BOOLEAN",
            JsonType.INTEGER: "BIGINT",
            JsonType.FLOAT: "DOUBLE PRECISION",
            JsonType.STRING: self._get_string_type(max_length),
            JsonType.ARRAY: "JSONB",  # Store arrays as JSONB
            JsonType.OBJECT: "JSONB",  # Store nested objects as JSONB
        }

        sql_type = type_mapping.get(json_type, "TEXT")
        return sql_type

    def _get_string_type(self, max_length: int) -> str:
        if max_length == 0:
            return "TEXT"
        elif max_length <= 255:
            return f"VARCHAR({max_length})"
        elif max_length <= 1000:
            return "VARCHAR(1000)"
        else:
            return "TEXT"

    def _sanitize_column_name(self, name: str) -> str:
        # Replace dots with underscores (flattened paths)
        name = name.replace(".", "_")

        # Remove brackets from array indicators
        name = name.replace("[]", "_array")

        # Convert to lowercase
        name = name.lower()

        # Replace any remaining non-alphanumeric with underscore
        name = "".join(c if c.isalnum() or c == "_" else "_" for c in name)

        # Ensure it doesn't start with a number
        if name and name[0].isdigit():
            name = f"col_{name}"

        # Reserved SQL keywords to avoid
        reserved = {"user", "group", "order", "table",
                    "index", "key", "value", "default"}
        if name in reserved:
            name = f"{name}_col"

        return name

    def generate_table_ddl(
        self,
        table_name: str,
        decision: SchemaDecision,
        include_audit_columns: bool = True
    ) -> str:
        """Generate CREATE TABLE DDL statement."""
        lines = []
        columns = []
        indexes = []

        # Always include an ID column
        columns.append("    id UUID PRIMARY KEY DEFAULT gen_random_uuid()")

        # Process each field from schema analysis
        field_definitions = self._generate_column_definitions(decision)
        columns.extend(field_definitions["columns"])
        indexes.extend(field_definitions["indexes"])

        # Add fallback JSONB column for unmapped fields
        if self.include_fallback_jsonb:
            columns.append("    extra JSONB")

        # Add audit columns
        if include_audit_columns:
            columns.append(
                "    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()")
            columns.append(
                "    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()")

        # Build CREATE TABLE statement
        lines.append(f"CREATE TABLE IF NOT EXISTS {table_name} (")
        lines.append(",\n".join(columns))
        lines.append(");")

        # Add indexes
        if indexes:
            lines.append("")
            lines.append(f"-- Indexes for {table_name}")
            for idx in indexes:
                lines.append(idx)

        # Add GIN index on extra JSONB column if included
        if self.include_fallback_jsonb:
            lines.append(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_extra ON {table_name} USING GIN (extra);")

        return "\n".join(lines)

    def _generate_column_definitions(
        self,
        decision: SchemaDecision
    ) -> Dict[str, List[str]]:
        columns = []
        indexes = []
        seen_columns: Set[str] = set()

        # Only process top-level fields (no dots in path)
        for field_path, field_info in decision.fields.items():
            # Skip nested fields and array indicators
            if "." in field_path or field_path.endswith("[]"):
                continue

            # Get field properties
            json_type = JsonType(field_info["dominant_type"])
            type_stability = field_info["type_stability"]
            presence = field_info["presence"]
            max_length = field_info.get("max_length", 0)
            is_likely_fk = field_info.get("is_likely_fk", False)

            # Sanitize column name
            col_name = self._sanitize_column_name(field_path)

            # Avoid duplicate columns
            if col_name in seen_columns:
                col_name = f"{col_name}_{len(seen_columns)}"
            seen_columns.add(col_name)

            # Determine SQL type
            sql_type = self._map_json_type_to_sql(json_type, max_length)

            # Determine nullability (if present in less than 95% of docs, make nullable)
            is_nullable = presence < 0.95
            nullable_clause = "" if is_nullable else " NOT NULL"

            # Build column definition
            column_def = f"    {col_name} {sql_type}{nullable_clause}"
            columns.append(column_def)

            # Add indexes for selective columns
            # Index if: high cardinality, frequently present, or likely FK
            should_index = (
                is_likely_fk or
                (presence > 0.8 and type_stability >
                 0.9 and json_type in [JsonType.INTEGER, JsonType.STRING])
            )

            if should_index:
                # Use appropriate index type
                if sql_type == "JSONB":
                    index_sql = f"CREATE INDEX IF NOT EXISTS idx_{col_name}_gin ON {{table_name}} USING GIN ({col_name});"
                else:
                    index_sql = f"CREATE INDEX IF NOT EXISTS idx_{col_name} ON {{table_name}} ({col_name});"
                indexes.append(index_sql)

        return {
            "columns": columns,
            "indexes": indexes,
        }

    def generate_jsonb_collection_ddl(
        self,
        collection_name: str,
        include_audit_columns: bool = True
    ) -> str:
        """Generate DDL for a JSONB document collection table."""
        lines = []

        lines.append(f"CREATE TABLE IF NOT EXISTS {collection_name} (")
        lines.append("    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),")
        lines.append("    doc JSONB NOT NULL")

        if include_audit_columns:
            lines.append(
                "    ,created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()")
            lines.append(
                "    ,updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()")

        lines.append(");")
        lines.append("")
        lines.append(f"-- GIN index for JSONB queries")
        lines.append(
            f"CREATE INDEX IF NOT EXISTS idx_{collection_name}_doc ON {collection_name} USING GIN (doc);")

        return "\n".join(lines)

    def generate_insert_statement(
        self,
        table_name: str,
        decision: SchemaDecision,
        placeholder_style: str = "named"
    ) -> str:
        """Generate INSERT statement template."""
        # Get top-level field names only
        columns = []
        for field_path in decision.fields.keys():
            if "." not in field_path and not field_path.endswith("[]"):
                col_name = self._sanitize_column_name(field_path)
                columns.append(col_name)

        # Add extra JSONB column if enabled
        if self.include_fallback_jsonb:
            columns.append("extra")

        # Generate placeholders
        if placeholder_style == "named":
            placeholders = [f":{col}" for col in columns]
        else:
            placeholders = ["%s"] * len(columns)

        insert_sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
        return insert_sql
