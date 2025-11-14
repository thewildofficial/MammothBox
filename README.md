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
- **Database Optimizations** (NEW ✅): Enhanced performance and monitoring
  - Connection pooling with QueuePool (10 base + 20 overflow)
  - Strategic GIN and composite indexes for sub-150ms queries
  - Automatic query timing and slow query warnings
- **OCR Text Detection** (NEW ✅): Searchable text extraction from images
  - Two-stage heuristic (edge density + OCR validation)
  - Tesseract-based text extraction with bounding boxes
  - Hybrid search combining vector similarity and keyword matching
  - Automatic detection of screenshots, diagrams, and memes
- **Recursive Folder Ingestion** (NEW ✅): Bulk import entire directory trees
  - Batch processing with progress tracking
  - `.allocatorignore` support (gitignore-style)
  - RESTful API for batch status monitoring
  - Support for images, videos, documents, and JSON
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
- **Storage Adapter**: Filesystem storage abstraction
- **Job Queue**: In-process queue (Redis optional for scaling)

See [docs/technical_specification.md](docs/technical_specification.md) for detailed technical documentation.

## Quick Start

**Recommended:** Use Docker for fastest setup (see [QUICKSTART.md](QUICKSTART.md))

### Docker Setup (Recommended)

```bash
# One-time base image build (~30 minutes)
docker build -f Dockerfile.base -t mammothbox-base:latest .

# Fast app build (~2 seconds)
docker-compose build
docker-compose up -d

# Verify it's running
curl http://localhost:8000/health
```

After the one-time base image build, subsequent code changes rebuild in ~2 seconds!

See [DOCKER_OPTIMIZATION.md](DOCKER_OPTIMIZATION.md) for details on the 1,350x speedup.

### Local Development Prerequisites

- Python 3.10+
- PostgreSQL 14+ with pgvector extension
- Docker & Docker Compose (recommended)
- ffmpeg (for video processing)
- Tesseract OCR (for text detection in images)

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

3. **Install system dependencies:**

**Ubuntu/Debian:**

```bash
sudo apt-get install tesseract-ocr ffmpeg
```

**macOS:**

```bash
brew install tesseract ffmpeg
```

**Windows:**

- Install Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki
- Install ffmpeg from: https://ffmpeg.org/download.html

4. **Start PostgreSQL with pgvector:**

```bash
docker-compose up -d postgres
```

5. **Run migrations:**

```bash
python scripts/migrate.py
```

6. **Start the application:**

```bash
python -m src.main
```

The API will be available at `http://localhost:8000`

### Docker Compose (Full Stack)

**Standard Build** (First time - 45 minutes):

```bash
docker-compose up -d
```

**Optimized Build for Hackathons** (5 seconds after initial setup):

```bash
# One-time setup (45 min - do before hackathon)
docker build -f Dockerfile.base -t mammothbox-base:latest .

# Update docker-compose.yml to use Dockerfile.optimized
# Then every rebuild is instant:
docker-compose build app  # 5 seconds!
docker-compose up -d       # Instant startup!
```

See [DOCKER_BUILD_OPTIMIZATION.md](DOCKER_BUILD_OPTIMIZATION.md) for details.

This starts:

- PostgreSQL with pgvector
- Application server (with pre-loaded CLIP model)
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
│   ├── storage/          # Storage abstraction
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
- `STORAGE_PATH`: Local filesystem path
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
3. **Storage Abstraction**: Filesystem-based storage
4. **CPU-Friendly**: No GPU required for MVP
5. **Idempotent**: All operations are auditable and replayable
6. **Human-in-the-Loop**: Schema and cluster decisions are provisional

## License

[Your License Here]

## Contributing

[Contributing guidelines]
