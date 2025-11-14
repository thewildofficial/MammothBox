"""Schema decision algorithm for SQL vs JSONB storage."""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from enum import Enum

from src.ingest.schema_analyzer import JsonSchemaAnalyzer
from src.config.settings import get_settings


class StorageChoice(str, Enum):
    SQL = "sql"
    JSONB = "jsonb"


@dataclass
class SchemaDecision:
    """Result of schema analysis and storage decision."""
    storage_choice: StorageChoice
    confidence: float  # 0-1 confidence in the decision
    reason: str  # Human-readable explanation

    # Analysis metadata
    documents_analyzed: int
    top_level_keys: int
    max_depth: int
    field_stability: float
    type_stability: float
    has_array_of_objects: bool
    structure_hash: str

    # Schema summary
    fields: Dict[str, Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "storage_choice": self.storage_choice.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "metadata": {
                "documents_analyzed": self.documents_analyzed,
                "top_level_keys": self.top_level_keys,
                "max_depth": self.max_depth,
                "field_stability": self.field_stability,
                "type_stability": self.type_stability,
                "has_array_of_objects": self.has_array_of_objects,
                "structure_hash": self.structure_hash,
            },
            "fields": self.fields,
        }


class SchemaDecider:
    """Decides optimal storage strategy for JSON documents."""

    def __init__(
        self,
        sample_size: Optional[int] = None,
        stability_threshold: Optional[float] = None,
        max_top_level_keys: Optional[int] = None,
        max_depth: Optional[int] = None,
    ):
        settings = get_settings()

        self.sample_size = sample_size or settings.schema_sample_size
        self.stability_threshold = stability_threshold or settings.schema_stability_threshold
        self.max_top_level_keys = max_top_level_keys or settings.schema_max_top_level_keys
        self.max_depth = max_depth or settings.schema_max_depth

    def decide(self, documents: List[Dict[str, Any]]) -> SchemaDecision:
        """Analyze documents and decide storage strategy."""
        # Analyze documents
        # Use a higher max_depth for analysis to discover true nesting depth
        # (we'll compare against self.max_depth for the decision)
        analyzer = JsonSchemaAnalyzer(
            # Analyze deeper to find true depth
            max_depth=max(self.max_depth + 3, 5),
            max_sample_size=self.sample_size
        )
        analyzer.analyze_batch(documents)
        summary = analyzer.get_summary()

        # Extract key metrics
        num_top_level = summary["top_level_keys"]
        max_depth = summary["max_depth"]
        field_stability = summary["field_stability"]
        type_stability = summary["type_stability"]
        has_arrays_of_objects = summary["has_array_of_objects"]

        # Decision logic with scoring
        sql_score = 0.0
        reasons = []

        # Rule 1: Check top-level key count
        if num_top_level <= self.max_top_level_keys:
            sql_score += 0.25
            reasons.append(
                f"✓ Manageable number of top-level keys ({num_top_level} ≤ {self.max_top_level_keys})")
        else:
            reasons.append(
                f"✗ Too many top-level keys ({num_top_level} > {self.max_top_level_keys})")

        # Rule 2: Check nesting depth
        if max_depth <= self.max_depth:
            sql_score += 0.25
            reasons.append(
                f"✓ Shallow nesting depth ({max_depth} ≤ {self.max_depth})")
        else:
            reasons.append(
                f"✗ Deep nesting detected ({max_depth} > {self.max_depth})")

        # Rule 3: Check field stability (presence across documents)
        if field_stability >= self.stability_threshold:
            sql_score += 0.25
            reasons.append(
                f"✓ High field stability ({field_stability:.2f} ≥ {self.stability_threshold})")
        else:
            reasons.append(
                f"✗ Low field stability ({field_stability:.2f} < {self.stability_threshold})")

        # Rule 4: Check type stability (consistent types)
        if type_stability >= 0.9:  # Require high type consistency
            sql_score += 0.15
            reasons.append(f"✓ Consistent field types ({type_stability:.2f})")
        else:
            reasons.append(
                f"✗ Inconsistent field types ({type_stability:.2f})")

        # Rule 5: Check for arrays of objects (problematic for SQL normalization)
        if not has_arrays_of_objects:
            sql_score += 0.10
            reasons.append("✓ No complex nested arrays")
        else:
            reasons.append(
                "✗ Contains arrays of objects (requires child tables)")

        # Make decision with hard vetos and stricter threshold
        # Hard veto #1: Arrays of objects are too complex for simple SQL tables
        if has_arrays_of_objects:
            choice = StorageChoice.JSONB
            confidence = 0.95
            reason = "JSONB storage required: " + "; ".join(reasons)
        # Hard veto #2: Too many top-level keys makes SQL impractical
        elif num_top_level > self.max_top_level_keys:
            choice = StorageChoice.JSONB
            confidence = 0.90
            reason = "JSONB storage required: " + "; ".join(reasons)
        # Hard veto #3: Deep nesting makes SQL impractical
        elif max_depth > self.max_depth:
            choice = StorageChoice.JSONB
            confidence = 0.90
            reason = "JSONB storage required: " + "; ".join(reasons)
        # SQL requires a high score (>= 0.85 = strict threshold)
        # This ensures only truly stable, well-structured data uses SQL
        elif sql_score >= 0.85:
            choice = StorageChoice.SQL
            confidence = sql_score
            reason = "SQL storage recommended: " + "; ".join(reasons)
        else:
            choice = StorageChoice.JSONB
            confidence = 1.0 - sql_score  # Invert score for JSONB confidence
            reason = "JSONB storage recommended: " + "; ".join(reasons)

        return SchemaDecision(
            storage_choice=choice,
            confidence=confidence,
            reason=reason,
            documents_analyzed=summary["documents_analyzed"],
            top_level_keys=num_top_level,
            max_depth=max_depth,
            field_stability=field_stability,
            type_stability=type_stability,
            has_array_of_objects=has_arrays_of_objects,
            structure_hash=summary["structure_hash"],
            fields=summary["fields"],
        )

    def explain_decision(self, decision: SchemaDecision) -> str:
        """Generate detailed explanation of the decision."""
        lines = [
            "=" * 60,
            "SCHEMA DECISION ANALYSIS",
            "=" * 60,
            f"Storage Choice: {decision.storage_choice.value.upper()}",
            f"Confidence: {decision.confidence:.1%}",
            "",
            "Analysis Results:",
            f"  • Documents Analyzed: {decision.documents_analyzed}",
            f"  • Top-Level Keys: {decision.top_level_keys}",
            f"  • Maximum Depth: {decision.max_depth}",
            f"  • Field Stability: {decision.field_stability:.2%}",
            f"  • Type Stability: {decision.type_stability:.2%}",
            f"  • Has Array of Objects: {decision.has_array_of_objects}",
            "",
            "Decision Rationale:",
            decision.reason,
            "=" * 60,
        ]
        return "\n".join(lines)

    def generate_collection_name(self, decision: SchemaDecision, hint: Optional[str] = None) -> str:
        """Generate a collection/table name from the schema."""
        # Generate hash-based fallback name
        hash_prefix = decision.structure_hash[:8]

        if hint:
            # Sanitize hint
            name = hint.lower().replace(" ", "_").replace("-", "_")
            # Remove non-alphanumeric characters except underscore
            name = "".join(c for c in name if c.isalnum() or c == "_")
            # Ensure name is valid: non-empty and starts with letter or underscore
            if name and (name[0].isalpha() or name[0] == "_"):
                return name
            # If sanitization produced invalid name, fall through to hash-based name

        # Generate from structure hash (shortened)
        if decision.storage_choice == StorageChoice.SQL:
            return f"table_{hash_prefix}"
        else:
            return f"docs_{hash_prefix}"
