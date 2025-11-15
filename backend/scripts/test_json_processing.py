#!/usr/bin/env python3
"""
Sample data generator and validation script.

Generates various JSON datasets to test the entire JSON processing pipeline.
"""

import json
import sys
from pathlib import Path

# Add project root to path before importing project modules
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.ingest.schema_decider import SchemaDecider, StorageChoice  # noqa: E402


# Sample datasets with different characteristics
SAMPLE_DATASETS = {
    "stable_users": {
        "description": "Stable schema - should choose SQL",
        "data": [
            {"id": 1, "name": "Alice Smith",
                "email": "alice@example.com", "age": 30, "active": True},
            {"id": 2, "name": "Bob Jones", "email": "bob@example.com",
                "age": 25, "active": False},
            {"id": 3, "name": "Charlie Brown",
                "email": "charlie@example.com", "age": 35, "active": True},
            {"id": 4, "name": "David Wilson",
                "email": "david@example.com", "age": 40, "active": True},
            {"id": 5, "name": "Eve Davis", "email": "eve@example.com",
                "age": 28, "active": False},
        ]
    },

    "unstable_events": {
        "description": "Unstable schema - should choose JSONB",
        "data": [
            {"event": "login", "user_id": 1, "timestamp": "2024-01-01T10:00:00Z"},
            {"event": "purchase", "order_id": 123,
                "total": 99.99, "currency": "USD"},
            {"event": "logout", "session_duration": 3600},
            {"event": "signup", "referrer": "google", "campaign": "summer2024"},
        ]
    },

    "nested_config": {
        "description": "Deeply nested - should choose JSONB",
        "data": [
            {
                "app": "web",
                "config": {
                    "database": {
                        "host": "localhost",
                        "port": 5432,
                        "credentials": {
                            "username": "admin",
                            "password": "secret"
                        }
                    },
                    "cache": {
                        "redis": {
                            "host": "cache.example.com",
                            "port": 6379
                        }
                    }
                }
            }
        ]
    },

    "products": {
        "description": "E-commerce products - moderate complexity",
        "data": [
            {"product_id": 1, "name": "Laptop", "price": 999.99, "category": "Electronics",
                "in_stock": True, "tags": ["computer", "portable"]},
            {"product_id": 2, "name": "Mouse", "price": 29.99, "category": "Electronics",
                "in_stock": True, "tags": ["accessory", "wireless"]},
            {"product_id": 3, "name": "Desk", "price": 299.99,
                "category": "Furniture", "in_stock": False, "tags": ["office"]},
            {"product_id": 4, "name": "Chair", "price": 199.99, "category": "Furniture",
                "in_stock": True, "tags": ["office", "ergonomic"]},
        ]
    },

    "complex_orders": {
        "description": "Orders with array of objects - should choose JSONB",
        "data": [
            {
                "order_id": 1001,
                "customer": "Alice Smith",
                "items": [
                    {"product_id": 1, "quantity": 1, "price": 999.99},
                    {"product_id": 2, "quantity": 2, "price": 29.99}
                ],
                "total": 1059.97
            },
            {
                "order_id": 1002,
                "customer": "Bob Jones",
                "items": [
                    {"product_id": 3, "quantity": 1, "price": 299.99}
                ],
                "total": 299.99
            }
        ]
    },

    "sensors": {
        "description": "IoT sensor data - time series",
        "data": [
            {"sensor_id": "temp_01", "reading": 22.5, "unit": "celsius",
                "timestamp": "2024-01-01T10:00:00Z", "location": "office"},
            {"sensor_id": "temp_01", "reading": 22.7, "unit": "celsius",
                "timestamp": "2024-01-01T10:05:00Z", "location": "office"},
            {"sensor_id": "humid_01", "reading": 45.2, "unit": "percent",
                "timestamp": "2024-01-01T10:00:00Z", "location": "warehouse"},
            {"sensor_id": "humid_01", "reading": 46.1, "unit": "percent",
                "timestamp": "2024-01-01T10:05:00Z", "location": "warehouse"},
        ]
    },

    "many_fields": {
        "description": "Too many fields - should choose JSONB",
        "data": [
            {f"field_{i}": f"value_{i}" for i in range(30)}
        ]
    }
}


def analyze_dataset(name: str, dataset: dict):
    """Analyze a dataset and print the decision."""
    print(f"\n{'=' * 70}")
    print(f"Dataset: {name}")
    print(f"Description: {dataset['description']}")
    print(f"Documents: {len(dataset['data'])}")
    print("=" * 70)

    # Analyze with schema decider
    decider = SchemaDecider()
    decision = decider.decide(dataset['data'])

    # Print decision
    print(f"\nStorage Choice: {decision.storage_choice.value.upper()}")
    print(f"Confidence: {decision.confidence:.1%}")
    print("\nAnalysis:")
    print(f"  • Documents Analyzed: {decision.documents_analyzed}")
    print(f"  • Top-Level Keys: {decision.top_level_keys}")
    print(f"  • Maximum Depth: {decision.max_depth}")
    print(f"  • Field Stability: {decision.field_stability:.2%}")
    print(f"  • Type Stability: {decision.type_stability:.2%}")
    print(f"  • Has Array of Objects: {decision.has_array_of_objects}")
    print(f"\nRationale:\n{decision.reason}")

    # Show field details
    print("\nField Details:")
    # Show first 10
    for field_path, field_info in sorted(decision.fields.items())[:10]:
        presence = field_info['presence']
        dtype = field_info['dominant_type']
        print(f"  • {field_path}: {dtype} (present in {presence:.0%} of docs)")

    if len(decision.fields) > 10:
        print(f"  ... and {len(decision.fields) - 10} more fields")

    return decision


def generate_sample_files():
    """Generate sample JSON files for testing."""
    output_dir = project_root / "tests" / "sample_data"
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, dataset in SAMPLE_DATASETS.items():
        output_file = output_dir / f"{name}.json"
        with open(output_file, 'w') as f:
            json.dump(dataset['data'], f, indent=2)
        print(f"Generated: {output_file}")


def main():
    """Run analysis on all sample datasets."""
    print("=" * 70)
    print("JSON SCHEMA ANALYSIS - SAMPLE DATASETS")
    print("=" * 70)

    results = {}
    for name, dataset in SAMPLE_DATASETS.items():
        decision = analyze_dataset(name, dataset)
        results[name] = decision.storage_choice

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print("=" * 70)

    sql_count = sum(1 for choice in results.values()
                    if choice == StorageChoice.SQL)
    jsonb_count = sum(1 for choice in results.values()
                      if choice == StorageChoice.JSONB)

    print(f"\nTotal Datasets: {len(results)}")
    print(f"SQL Storage: {sql_count}")
    print(f"JSONB Storage: {jsonb_count}")

    print("\nDetailed Results:")
    for name, choice in results.items():
        emoji = "📊" if choice == StorageChoice.SQL else "📝"
        print(f"  {emoji} {name}: {choice.value.upper()}")

    # Generate sample files
    print(f"\n{'=' * 70}")
    print("GENERATING SAMPLE FILES")
    print("=" * 70)
    generate_sample_files()

    print("\n✅ Analysis complete!")


if __name__ == "__main__":
    main()
