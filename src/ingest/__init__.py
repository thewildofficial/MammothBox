"""
Ingest module for JSON processing.

Provides schema analysis, decision algorithms, and DDL generation
for intelligent JSON document storage.
"""

from src.ingest.schema_analyzer import (
    JsonSchemaAnalyzer,
    JsonType,
    FieldStats,
    flatten_json,
    detect_json_type,
)
from src.ingest.schema_decider import (
    SchemaDecider,
    SchemaDecision,
    StorageChoice,
)
from src.ingest.ddl_generator import DDLGenerator
from src.ingest.json_processor import JsonProcessor, JsonProcessingError

__all__ = [  # ruff: noqa: RUF022
    # Schema Analysis
    "JsonSchemaAnalyzer",
    "JsonType",
    "FieldStats",
    "flatten_json",
    "detect_json_type",
    # Decision Making
    "SchemaDecider",
    "SchemaDecision",
    "StorageChoice",
    # DDL Generation
    "DDLGenerator",
    # Processing
    "JsonProcessor",
    "JsonProcessingError",
]
