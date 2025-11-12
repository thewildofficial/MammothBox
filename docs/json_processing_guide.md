# JSON Processing System - MammothBox

Intelligent JSON document storage system that automatically analyzes structure and decides between SQL and JSONB storage.

## Features

✅ **Automatic Schema Detection**: Analyzes JSON documents to detect structure patterns
✅ **Smart Storage Decisions**: Chooses SQL for stable schemas, JSONB for flexible documents  
✅ **DDL Generation**: Automatically generates CREATE TABLE statements with proper types
✅ **Human-in-the-Loop**: Provisional schemas require admin approval before activation
✅ **Complete Audit Trail**: Tracks every processing stage in lineage table
✅ **RESTful API**: Simple endpoints for ingestion and schema management

## Quick Start

### 1. Set up the database

```bash
# Start PostgreSQL with pgvector
docker-compose up -d postgres

# Run migrations
python scripts/migrate.py
```

### 2. Start the API server

```bash
python -m src.main
```

The API will be available at `http://localhost:8000`

### 3. Ingest JSON documents

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -F 'payload=[{"id": 1, "name": "Alice", "age": 30}, {"id": 2, "name": "Bob", "age": 25}]' \
  -F 'owner=demo' \
  -F 'collection_name=users'
```

## API Endpoints

### Ingestion

**POST /api/v1/ingest**

Ingest JSON documents for processing.

Parameters:

- `payload` (required): JSON object or array as string
- `owner` (optional): Owner identifier
- `collection_name` (optional): Hint for collection/table name
- `comments` (optional): Additional metadata

Response:

```json
{
  "job_id": "uuid",
  "system_ids": ["uuid1", "uuid2"],
  "status": "provisional",
  "message": "Processed 2 documents. Storage: sql"
}
```

### Schema Management

**GET /api/v1/schemas**

List all schema definitions.

Query parameters:

- `status`: Filter by status (provisional, active, rejected)

**GET /api/v1/schemas/{schema_id}**

Get details of a specific schema.

**POST /api/v1/schemas/{schema_id}/approve**

Approve a provisional schema and execute DDL.

Parameters:

- `reviewed_by`: Identifier of reviewer

**POST /api/v1/schemas/{schema_id}/reject**

Reject a provisional schema.

Parameters:

- `reviewed_by`: Identifier of reviewer
- `reason`: Rejection reason

## Schema Decision Algorithm

The system analyzes JSON documents and decides storage based on:

### Prefers SQL when:

- ✓ ≤ 20 top-level keys
- ✓ ≤ 2 nesting depth
- ✓ ≥ 60% field stability (fields present across documents)
- ✓ ≥ 90% type stability (consistent data types)
- ✓ No arrays of objects

### Prefers JSONB when:

- ✗ Many top-level keys (> 20)
- ✗ Deep nesting (> 2 levels)
- ✗ Unstable fields (< 60% presence)
- ✗ Inconsistent types
- ✗ Contains arrays of objects

## Examples

### Example 1: Stable Schema → SQL

Input:

```json
[
  { "id": 1, "name": "Alice", "email": "alice@example.com", "age": 30 },
  { "id": 2, "name": "Bob", "email": "bob@example.com", "age": 25 },
  { "id": 3, "name": "Charlie", "email": "charlie@example.com", "age": 35 }
]
```

Decision: **SQL** (stable fields, simple structure)

Generated DDL:

```sql
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    id_col BIGINT,
    name VARCHAR(255),
    email VARCHAR(255),
    age BIGINT,
    extra JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);
```

### Example 2: Unstable Schema → JSONB

Input:

```json
[
  { "event": "login", "user_id": 1 },
  { "event": "purchase", "order_id": 123, "total": 99.99 },
  { "event": "logout", "session_duration": 3600 }
]
```

Decision: **JSONB** (varying fields, flexible structure)

Generated DDL:

```sql
CREATE TABLE IF NOT EXISTS docs_abc12345 (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc JSONB NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_docs_abc12345_doc ON docs_abc12345 USING GIN (doc);
```

## Testing

### Run unit tests

```bash
pytest tests/unit/
```

### Test with sample data

```bash
python scripts/test_json_processing.py
```

This will analyze various JSON datasets and show decision rationale.

## Configuration

Edit `.env` or set environment variables:

```bash
# Schema decision thresholds
SCHEMA_SAMPLE_SIZE=128              # Max documents to analyze
SCHEMA_STABILITY_THRESHOLD=0.6      # Min field stability for SQL
SCHEMA_MAX_TOP_LEVEL_KEYS=20        # Max top-level keys for SQL
SCHEMA_MAX_DEPTH=2                  # Max nesting depth for SQL

# Auto-migration (set to true to skip approval step)
AUTO_MIGRATE=false                  # Require admin approval for schemas
```

## Architecture

```
JSON Documents
      ↓
[Schema Analyzer] → Flatten, detect types, compute statistics
      ↓
[Schema Decider] → Apply heuristics, decide SQL vs JSONB
      ↓
[DDL Generator] → Generate CREATE TABLE statements
      ↓
[Provisional Schema] → Requires admin approval
      ↓
[Active Schema] → DDL executed, ready for data
```

## Database Schema

### Tables Created:

- `asset_raw`: Immutable raw upload records
- `asset`: Canonical metadata for processed documents
- `schema_def`: JSON schema definitions and decisions
- `lineage`: Complete audit trail
- Dynamic tables: Created per schema as `table_*` or `docs_*`

## Development

### Project Structure

```
src/
├── ingest/
│   ├── schema_analyzer.py    # JSON flattening and analysis
│   ├── schema_decider.py     # Decision algorithm
│   ├── ddl_generator.py      # SQL DDL generation
│   └── json_processor.py     # Main orchestrator
├── catalog/
│   ├── models.py              # SQLAlchemy models
│   └── database.py            # Database connections
└── api/
    └── routes.py              # FastAPI endpoints
```

### Adding Custom Decision Rules

Edit `src/ingest/schema_decider.py` and modify the `decide()` method:

```python
def decide(self, documents):
    # ... existing analysis ...

    # Add custom rule
    if custom_condition:
        sql_score += 0.1
        reasons.append("Custom rule matched")

    # ... rest of logic ...
```

## Troubleshooting

### Schema stuck in provisional state

Approve manually:

```bash
curl -X POST http://localhost:8000/api/v1/schemas/{schema_id}/approve \
  -F 'reviewed_by=admin'
```

Or enable auto-migration in settings:

```bash
AUTO_MIGRATE=true
```

### Check processing status

Query lineage table:

```sql
SELECT * FROM lineage WHERE request_id = 'your-request-id' ORDER BY created_at;
```

## Future Enhancements

- [ ] Actual SQL data insertion (currently creates asset records only)
- [ ] Schema evolution and migration support
- [ ] Query API for stored JSON documents
- [ ] Performance optimizations for large batches
- [ ] Admin UI for schema management
- [ ] Metrics and monitoring dashboard

## License

Part of the MammothBox project.
