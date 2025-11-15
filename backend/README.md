# MammothBox Backend

FastAPI-based backend service for the MammothBox file allocation system.

## Features

- **Media Processing**: CLIP embeddings, clustering, deduplication
- **Document Processing**: PDF/DOCX parsing, chunking, embedding with sentence-transformers
- **Semantic Search**: Vector similarity search with pgvector
- **Job Queue**: Async processing with in-process or Redis queue
- **Admin Operations**: Cluster management, schema approval

## Quick Start

```bash
cd backend

# Build base image (one-time, ~30 minutes)
docker build -f Dockerfile.base -t mammothbox-base:latest .

# Build and run
docker-compose build
docker-compose up -d

# Check health
curl http://localhost:8000/health
```

## Development

```bash
# Install dependencies
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run tests
pytest

# Run locally (requires PostgreSQL and Redis)
python -m src.main
```

## API Endpoints

- `GET /` - Service info
- `GET /health` - Health check
- `GET /ready` - Readiness check
- `POST /api/v1/ingest` - Upload files
- `GET /api/v1/ingest/{job_id}/status` - Job status
- `GET /api/v1/search` - Semantic search
- `GET /api/v1/objects/{id}` - Get asset details
- `GET /api/v1/admin/clusters` - List clusters
- `GET /api/v1/admin/clusters/statistics` - Cluster stats

See [docs/API.md](docs/API.md) for complete API documentation.

## Project Structure

```
backend/
├── src/                    # Source code
│   ├── api/               # FastAPI routes
│   ├── catalog/           # Database models and queries
│   ├── media/             # Media processing (CLIP, clustering)
│   ├── documents/         # Document processing
│   ├── ingest/            # Ingestion orchestration
│   ├── queue/             # Job queue management
│   ├── storage/           # Storage adapters
│   ├── admin/             # Admin operations
│   └── config/            # Configuration
├── migrations/            # Database migrations
├── scripts/               # Utility scripts
├── tests/                 # Test suite
├── storage/               # File storage (mounted volume)
└── docs/                  # Documentation
```

## Docker Optimization

This project uses a two-stage Docker build for fast iteration:

- **Base image** (~30 min build): System dependencies, Python packages, ML models
- **App image** (~2 sec rebuild): Just application code

See [../DOCKER_OPTIMIZATION.md](../DOCKER_OPTIMIZATION.md) for details.

## Performance

- Docker rebuild: **1.5-3 seconds** (1,350x speedup from 45 minutes)
- CLIP model: Pre-loaded in base image (instant startup)
- All endpoints tested and working
