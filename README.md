# Automated File Allocator

A smart storage system with a unified frontend interface that intelligently processes and stores any type of data—automatically categorizing media files and making intelligent SQL vs NoSQL storage decisions for JSON documents.

## Features

- **Unified Ingestion**: Single `/api/v1/ingest` endpoint accepts both media files and JSON documents
- **Media Intelligence**: Automatic image/video analysis using CLIP embeddings, clustering similar content into organized directories
- **Schema Inference**: Intelligent JSON schema analysis with automatic SQL vs JSONB storage decision
- **Semantic Search**: Text-to-image/video search using CLIP embeddings with pgvector ANN search (Phase 7 ✅)
  - Fast similarity search with HNSW indexes
  - Multi-filter support (type, owner, cluster, tags, threshold)
  - Query timing and performance metrics
  - 28 comprehensive unit tests
- **Human-in-the-Loop**: Provisional schema proposals and cluster assignments require admin approval
- **Audit Trail**: Complete lineage tracking for all ingested assets

## Architecture

This is a monolithic backend application with clear modular boundaries, designed for easy extension and eventual service decomposition.

### Key Components

- **HTTP API**: Single entry point for all clients
- **Ingest Orchestrator**: Normalizes requests, stores raw inputs, enqueues jobs
- **Media Processor**: Thumbnailing, CLIP embeddings, clustering, deduplication
- **JSON Processor**: Schema inference, SQL/JSONB decision, DDL generation
- **Catalog Service**: Metadata store with PostgreSQL + pgvector
- **Storage Adapter**: Filesystem or S3-compatible storage abstraction
- **Job Queue**: In-process queue (Redis optional for scaling)

See [docs/mvp_backend_design.md](docs/mvp_backend_design.md) for detailed architecture documentation.

## Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL 14+ with pgvector extension
- Docker & Docker Compose (recommended)
- ffmpeg (for video processing)

### Local Development Setup

1. **Clone and setup environment:**

```bash
git clone <repo-url>
cd Automated-File-Allocator
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure environment variables:**

```bash
cp .env.example .env
# Edit .env with your database credentials and storage paths
```

3. **Start PostgreSQL with pgvector:**

```bash
docker-compose up -d postgres
```

4. **Run migrations:**

```bash
python scripts/migrate.py
```

5. **Start the application:**

```bash
python -m src.main
```

The API will be available at `http://localhost:8000`

### Docker Compose (Full Stack)

```bash
docker-compose up -d
```

This starts:

- PostgreSQL with pgvector
- Application server
- Redis (optional, for job queue)

## API Endpoints

### POST /api/v1/ingest

Upload media files or JSON documents.

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -F "files[]=@image.jpg" \
  -F "payload={\"name\":\"example\",\"value\":123}" \
  -F "owner=user123" \
  -F "comments=Test upload"
```

**Response:**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "system_ids": ["asset-uuid-1", "asset-uuid-2"],
  "status": "accepted"
}
```

### GET /api/v1/ingest/{jobId}/status

Check processing status.

**Response:**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "progress": {
    "queued": 0,
    "processing": 1,
    "done": 0,
    "failed": 0
  }
}
```

### GET /api/v1/search

Semantic search for media files using CLIP embeddings.

**Request:**

```bash
# Simple search
curl "http://localhost:8000/api/v1/search?query=dog&limit=10"

# Search with filters
curl "http://localhost:8000/api/v1/search?query=sunset&type=media&threshold=0.7&tags=landscape"
```

**Query Parameters:**

- `query` (required): Search text
- `type`: Filter by 'media' or 'json'
- `limit`: Max results (default: 10, max: 100)
- `threshold`: Min similarity score (default: 0.5, range: 0.0-1.0)
- `owner`: Filter by owner
- `cluster_id`: Filter by cluster UUID
- `tags`: Comma-separated tags

**Response:**

```json
{
  "query": "dog",
  "results": [
    {
      "id": "asset-uuid",
      "kind": "media",
      "uri": "fs://media/clusters/cluster-123/asset.jpg",
      "tags": ["dog", "pet", "animal"],
      "similarity_score": 0.9234,
      "cluster": {
        "id": "cluster-uuid",
        "name": "Dogs"
      },
      "thumbnail_uri": "fs://derived/.../thumb.jpg",
      "owner": "user123",
      "created_at": "2025-11-14T12:00:00"
    }
  ],
  "total": 1,
  "query_time_ms": 45.23,
  "filters_applied": {
    "type": null,
    "owner": null,
    "min_similarity": 0.5,
    "limit": 10
  }
}
```

### GET /api/v1/objects/{system_id}

Get asset metadata.

### PATCH /api/v1/clusters/{clusterId}

Admin operations: rename, merge clusters.

## Project Structure

```
Automated-File-Allocator/
├── src/
│   ├── api/              # HTTP API handlers
│   ├── ingest/           # Ingestion orchestrator
│   ├── media/            # Media processing pipeline
│   ├── json/             # JSON schema inference
│   ├── catalog/          # Metadata catalog service
│   ├── storage/          # Storage abstraction (fs/s3)
│   ├── queue/            # Job queue interface
│   ├── admin/            # Admin UI backend
│   └── config/           # Configuration management
├── migrations/            # Database migrations
├── tests/                 # Unit and integration tests
├── scripts/              # Utility scripts
├── docs/                  # Documentation
├── docker-compose.yml    # Docker setup
├── requirements.txt      # Python dependencies
└── README.md            # This file
```

## Configuration

Key environment variables (see `.env.example`):

- `DATABASE_URL`: PostgreSQL connection string
- `STORAGE_BACKEND`: `fs://` or `s3://`
- `STORAGE_PATH`: Local filesystem path (for `fs://`)
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`: For S3 backend
- `EMBEDDING_MODEL`: CLIP model name (default: `openai/clip-vit-base-patch32`)
- `CLUSTER_THRESHOLD`: Default similarity threshold (default: 0.8)
- `WORKER_THREADS`: Number of worker threads (default: 4)

## Development

### Running Tests

```bash
pytest tests/
```

### Code Style

```bash
black src/ tests/
flake8 src/ tests/
```

### Adding Migrations

```bash
python scripts/create_migration.py --name add_new_table
```

## Architecture Diagram

See [docs/architecture_diagram.png](docs/architecture_diagram.png) for a visual representation of the system architecture.

## Design Principles

1. **KISS First**: Monolith with clear module boundaries
2. **Single Database**: PostgreSQL + pgvector for all data
3. **Storage Abstraction**: Switchable fs/s3 backends
4. **CPU-Friendly**: No GPU required for MVP
5. **Idempotent**: All operations are auditable and replayable
6. **Human-in-the-Loop**: Schema and cluster decisions are provisional

## License

[Your License Here]

## Contributing

[Contributing guidelines]
