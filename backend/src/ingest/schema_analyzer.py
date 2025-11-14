"""JSON schema analyzer and flattener."""

import hashlib
import json
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple, Optional
from enum import Enum


class JsonType(str, Enum):
    NULL = "null"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    FLOAT = "float"
    STRING = "string"
    ARRAY = "array"
    OBJECT = "object"


class FieldStats:

    def __init__(self, path: str):
        self.path = path
        self.type_counts: Dict[JsonType, int] = defaultdict(int)
        self.presence_count = 0
        self.null_count = 0
        self.sample_values: List[Any] = []
        self.max_value_length = 0

    def add_value(self, value: Any, json_type: JsonType) -> None:
        self.presence_count += 1
        self.type_counts[json_type] += 1

        if value is None:
            self.null_count += 1

        # Keep sample values (max 10)
        if len(self.sample_values) < 10:
            self.sample_values.append(value)

        # Track max length for strings
        if json_type == JsonType.STRING and value:
            self.max_value_length = max(self.max_value_length, len(str(value)))

    def get_dominant_type(self) -> Tuple[JsonType, float]:
        """Get the most common type and its fraction."""
        if not self.type_counts:
            return (JsonType.NULL, 1.0)

        total = sum(self.type_counts.values())
        dominant = max(self.type_counts.items(), key=lambda x: x[1])
        type_stability = dominant[1] / total if total > 0 else 0.0

        return (dominant[0], type_stability)

    def get_presence_fraction(self, total_docs: int) -> float:
        return self.presence_count / total_docs if total_docs > 0 else 0.0

    def is_likely_foreign_key(self) -> bool:
        path_lower = self.path.lower()
        return (
            path_lower.endswith('_id') or
            path_lower.endswith('_key') or
            'id' in path_lower
        )


def detect_json_type(value: Any) -> JsonType:
    if value is None:
        return JsonType.NULL
    elif isinstance(value, bool):
        return JsonType.BOOLEAN
    elif isinstance(value, int):
        return JsonType.INTEGER
    elif isinstance(value, float):
        return JsonType.FLOAT
    elif isinstance(value, str):
        return JsonType.STRING
    elif isinstance(value, list):
        return JsonType.ARRAY
    elif isinstance(value, dict):
        return JsonType.OBJECT
    else:
        return JsonType.STRING  # Fallback


def flatten_json(
    obj: Dict[str, Any],
    max_depth: int = 3,
    parent_path: str = "",
    current_depth: int = 0
) -> Dict[str, Tuple[Any, JsonType, int]]:
    result = {}

    if not isinstance(obj, dict):
        return result

    for key, value in obj.items():
        # Build the path
        path = f"{parent_path}.{key}" if parent_path else key
        depth = current_depth + 1
        json_type = detect_json_type(value)

        # Always record the path
        result[path] = (value, json_type, depth)

        # Recursively flatten nested objects if within depth limit
        if json_type == JsonType.OBJECT and depth < max_depth:
            nested = flatten_json(value, max_depth, path, depth)
            result.update(nested)

        # For arrays, check if it's an array of objects
        elif json_type == JsonType.ARRAY and depth < max_depth and value:
            # Sample first item to detect array of objects
            if value and isinstance(value[0], dict):
                # Mark as array of objects (special handling needed)
                result[f"{path}[]"] = (value, JsonType.ARRAY, depth)

    return result


class JsonSchemaAnalyzer:
    """Analyzer for JSON document collections."""

    def __init__(self, max_depth: int = 3, max_sample_size: int = 128):
        self.max_depth = max_depth
        self.max_sample_size = max_sample_size
        self.field_stats: Dict[str, FieldStats] = {}
        self.documents_analyzed = 0
        self.max_observed_depth = 0
        self.top_level_keys: Set[str] = set()

    def analyze_document(self, doc: Dict[str, Any]) -> None:
        if self.documents_analyzed >= self.max_sample_size:
            return

        self.documents_analyzed += 1

        # Track top-level keys
        if isinstance(doc, dict):
            self.top_level_keys.update(doc.keys())

        # Flatten and analyze
        flattened = flatten_json(doc, self.max_depth)

        for path, (value, json_type, depth) in flattened.items():
            # Track maximum depth
            self.max_observed_depth = max(self.max_observed_depth, depth)

            # Get or create field stats
            if path not in self.field_stats:
                self.field_stats[path] = FieldStats(path)

            # Record value
            self.field_stats[path].add_value(value, json_type)

    def analyze_batch(self, documents: List[Dict[str, Any]]) -> None:
        # Sample if necessary
        if len(documents) > self.max_sample_size:
            import random
            documents = random.sample(documents, self.max_sample_size)

        for doc in documents:
            self.analyze_document(doc)

    def get_field_stability(self) -> float:
        """Calculate overall field stability across all fields."""
        if not self.field_stats:
            return 0.0

        # Calculate average presence fraction for top-level fields
        top_level_stats = [
            stats for path, stats in self.field_stats.items()
            if '.' not in path and not path.endswith('[]')
        ]

        if not top_level_stats:
            return 0.0

        total_presence = sum(
            stats.get_presence_fraction(self.documents_analyzed)
            for stats in top_level_stats
        )

        return total_presence / len(top_level_stats) if top_level_stats else 0.0

    def get_type_stability(self) -> float:
        """Calculate overall type stability across all fields."""
        if not self.field_stats:
            return 0.0

        type_stabilities = [
            stats.get_dominant_type()[1]
            for stats in self.field_stats.values()
        ]

        return sum(type_stabilities) / len(type_stabilities) if type_stabilities else 0.0

    def has_array_of_objects(self) -> bool:
        return any(
            path.endswith('[]')
            for path in self.field_stats.keys()
        )

    def get_structure_hash(self) -> str:
        """Generate a hash representing the structure."""
        # Create a stable representation of the schema
        schema_repr = {
            path: str(stats.get_dominant_type()[0])
            for path, stats in sorted(self.field_stats.items())
        }

        schema_str = json.dumps(schema_repr, sort_keys=True)
        return hashlib.sha256(schema_str.encode()).hexdigest()

    def get_summary(self) -> Dict[str, Any]:
        return {
            "documents_analyzed": self.documents_analyzed,
            "total_fields": len(self.field_stats),
            "top_level_keys": len(self.top_level_keys),
            "max_depth": self.max_observed_depth,
            "field_stability": self.get_field_stability(),
            "type_stability": self.get_type_stability(),
            "has_array_of_objects": self.has_array_of_objects(),
            "structure_hash": self.get_structure_hash(),
            "fields": {
                path: {
                    "dominant_type": stats.get_dominant_type()[0].value,
                    "type_stability": stats.get_dominant_type()[1],
                    "presence": stats.get_presence_fraction(self.documents_analyzed),
                    "null_fraction": stats.null_count / stats.presence_count if stats.presence_count > 0 else 0,
                    "max_length": stats.max_value_length,
                    "is_likely_fk": stats.is_likely_foreign_key(),
                }
                for path, stats in self.field_stats.items()
            }
        }
