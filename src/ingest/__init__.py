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
from src.ingest.validator import (
    IngestValidator,
    ValidationResult,
    FileValidationResult,
    JsonValidationResult,
    AssetKind,
    MAX_IMAGE_SIZE,
    MAX_VIDEO_SIZE,
    MAX_AUDIO_SIZE,
    MAX_JSON_SIZE,
    MAX_DOCUMENT_SIZE,
)
from src.ingest.orchestrator import IngestionOrchestrator, OrchestrationError

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
    # Validation
    "IngestValidator",
    "ValidationResult",
    "FileValidationResult",
    "JsonValidationResult",
    "AssetKind",
    "MAX_IMAGE_SIZE",
    "MAX_VIDEO_SIZE",
    "MAX_AUDIO_SIZE",
    "MAX_JSON_SIZE",
    "MAX_DOCUMENT_SIZE",
    # Orchestration
    "IngestionOrchestrator",
    "OrchestrationError",
]
