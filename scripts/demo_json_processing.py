#!/usr/bin/env python3
"""
Quick demo script for JSON processing.

Demonstrates the complete JSON ingestion flow with sample data.
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def demo_schema_analysis():
    """Demonstrate schema analysis without database."""
    print("=" * 70)
    print("DEMO: JSON Schema Analysis")
    print("=" * 70)

    from src.ingest.schema_decider import SchemaDecider

    # Example 1: Stable schema (should choose SQL)
    print("\n1. Analyzing stable user data...")
    users = [
        {"id": 1, "name": "Alice", "email": "alice@example.com", "age": 30},
        {"id": 2, "name": "Bob", "email": "bob@example.com", "age": 25},
        {"id": 3, "name": "Charlie", "email": "charlie@example.com", "age": 35},
    ]

    decider = SchemaDecider()
    decision = decider.decide(users)

    print(f"\n   Storage Choice: {decision.storage_choice.value.upper()}")
    print(f"   Confidence: {decision.confidence:.0%}")
    print(f"   Reason: {decision.reason[:100]}...")

    # Example 2: Unstable schema (should choose JSONB)
    print("\n2. Analyzing unstable event data...")
    events = [
        {"event": "login", "user_id": 1},
        {"event": "purchase", "order_id": 123, "total": 99.99},
        {"event": "logout", "duration": 3600},
    ]

    decision = decider.decide(events)

    print(f"\n   Storage Choice: {decision.storage_choice.value.upper()}")
    print(f"   Confidence: {decision.confidence:.0%}")
    print(f"   Reason: {decision.reason[:100]}...")


def demo_ddl_generation():
    """Demonstrate DDL generation."""
    print("\n" + "=" * 70)
    print("DEMO: DDL Generation")
    print("=" * 70)

    from src.ingest.schema_decider import SchemaDecider, StorageChoice
    from src.ingest.ddl_generator import DDLGenerator

    # Generate SQL table DDL
    print("\n1. SQL Table DDL:")
    docs = [
        {"id": 1, "name": "Product A", "price": 99.99, "in_stock": True},
        {"id": 2, "name": "Product B", "price": 149.99, "in_stock": False},
    ]

    decider = SchemaDecider()
    decision = decider.decide(docs)

    if decision.storage_choice == StorageChoice.SQL:
        generator = DDLGenerator()
        ddl = generator.generate_table_ddl("products", decision)
        print("\n" + ddl[:500] + "...")

    # Generate JSONB collection DDL
    print("\n2. JSONB Collection DDL:")
    generator = DDLGenerator()
    ddl = generator.generate_jsonb_collection_ddl("docs_events")
    print("\n" + ddl)


def demo_api_usage():
    """Show example API usage."""
    print("\n" + "=" * 70)
    print("DEMO: API Usage Examples")
    print("=" * 70)

    print("\n1. Ingest JSON documents:")
    print("""
    curl -X POST http://localhost:8000/api/v1/ingest \\
      -F 'payload=[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]' \\
      -F 'owner=demo' \\
      -F 'collection_name=users'
    """)

    print("\n2. List schemas:")
    print("""
    curl http://localhost:8000/api/v1/schemas?status=provisional
    """)

    print("\n3. Approve a schema:")
    print("""
    curl -X POST http://localhost:8000/api/v1/schemas/{schema_id}/approve \\
      -F 'reviewed_by=admin'
    """)


def main():
    """Run all demos."""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "MammothBox JSON Processing Demo" + " " * 21 + "║")
    print("╚" + "═" * 68 + "╝")

    try:
        demo_schema_analysis()
        demo_ddl_generation()
        demo_api_usage()

        print("\n" + "=" * 70)
        print("Next Steps:")
        print("=" * 70)
        print("\n1. Start the database:")
        print("   docker-compose up -d postgres")
        print("\n2. Run migrations:")
        print("   python scripts/migrate.py")
        print("\n3. Start the API server:")
        print("   python -m src.main")
        print("\n4. Try the sample data script:")
        print("   python scripts/test_json_processing.py")
        print("\n5. Run tests:")
        print("   pytest tests/unit/")
        print("\n✅ Demo complete!\n")

    except Exception as e:
        print(f"\n❌ Error running demo: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
