<<<<<<< HEAD
# ⚠️ MammothBox (DEPRECATED)

> **⚠️ This project is archived and no longer maintained.**  
> **Reason:** Over-engineered for hackathon requirements - judges wanted simple storage/retrieval, we built an AI research project.
>
> **📖 [Read full deprecation notice →](./DEPRECATED.md)**

---

# MammothBox - Automated File Allocator

**Status:** 🗄️ Archived (November 2025)  
**Reason:** Rejected from hackathon for being too complex - they wanted simple storage, we built AI classification system

## What This Was

An over-engineered intelligent file organization system with:
- AI-powered image/video/audio analysis (BLIP-2, Whisper, Phi-3.5)
- Semantic clustering with CLIP embeddings
- VLM metadata extraction
- Automatic file organization
- Perceptual deduplication

## What They Actually Wanted

```python
@app.post("/upload")  # Upload file
@app.get("/download/{file_id}")  # Download file
@app.get("/search?q=filename")  # Search files
```

Yeah... we missed the mark. 🎯❌

## Lessons Learned

**Don't classify when they asked for storage.**

Read the full story and technical details in [DEPRECATED.md](./DEPRECATED.md).

---

<details>
<summary><b>📋 Original README (click to expand)</b></summary>

# Automated File Allocator


A smart storage system with a unified frontend interface that intelligently processes and stores any type of data—automatically categorizing media files and making intelligent SQL vs NoSQL storage decisions for JSON documents.
=======
# MammothBox - Intelligent Multi-Modal Storage System

> **Hackathon Problem Statement 2**: Design a smart storage system with a single frontend interface that intelligently processes and stores any type of data.
>>>>>>> ed35e5d73c5c91061e049c14356a05baa9f28173

**Status**: 60-70% feature complete | [Architecture](ARCHITECTURE.md) | [Roadmap](ROADMAP.md) | [Quick Start](QUICKSTART.md)

## What is MammothBox?

MammothBox is an intelligent storage system that automatically:

1. **For Media Files** (images/videos):
   - ✅ Analyzes content using AI (CLIP embeddings)
   - ✅ Groups similar media into organized directories
   - ✅ Creates new categories for unique content
   - ✅ Enables semantic search ("find beach photos")

2. **For JSON Data**:
   - ✅ Determines if SQL or NoSQL storage is appropriate
   - ✅ Generates database schemas automatically
   - ✅ Detects relationships between multiple JSON objects
   - ✅ Creates hybrid structures (SQL + JSONB) when needed

3. **Unified Interface**:
   - ✅ Single API endpoint accepts all file types
   - ✅ Batch processing with progress tracking
   - ✅ Optional comments/metadata to guide decisions
   - 🚧 React frontend (in progress)

## Project Structure

```
MammothBox/
├── backend/              # FastAPI backend (COMPLETE)
│   ├── src/             # Core application logic
│   ├── tests/           # 89% code coverage
│   ├── migrations/      # Database schema
│   └── docs/            # API documentation
├── frontend/
│   └── mammothbox/      # React TypeScript app (SCAFFOLD)
├── ARCHITECTURE.md      # Design decisions explained
├── ROADMAP.md          # Future plans & timeline
├── QUICKSTART.md       # Setup instructions
└── README.md           # This file
```

## Problem Statement Requirements

### ✅ Implemented (60-70% Complete)

#### Media Files
- ✅ **Unified frontend** - Single upload interface for all media types
- ✅ **Automatic analysis** - CLIP AI embeddings extract semantic meaning
- ✅ **Smart categorization** - HDBSCAN clustering groups similar content
- ✅ **Directory organization** - Files stored in `/clusters/<category_id>/`
- ✅ **Subsequent media routing** - New uploads join existing clusters automatically
- ✅ **Video support** - Keyframe extraction with diversity filtering
- ✅ **Semantic search** - "Find beach photos" works across all media

#### Structured Data (JSON)
- ✅ **Unified frontend** - Same endpoint accepts JSON files
- ✅ **SQL vs NoSQL decision** - Heuristic scoring (consistency, nesting, arrays)
- ✅ **Automatic schema generation** - DDL created from JSON structure
- ✅ **Relationship detection** - Foreign keys identified by naming conventions
- ✅ **Batch analysis** - Multiple JSONs analyzed together for complete schema
- ✅ **Hybrid storage** - SQL columns + JSONB for flexible fields

#### Additional Requirements
- ✅ **Comments/metadata support** - Optional `comment` field guides decisions
- ✅ **Batch inputs** - Folder upload with progress tracking
- ✅ **Query optimization** - HNSW indexes, connection pooling, sub-150ms queries
- ✅ **Consistency** - Provisional state requires admin approval before final storage

### 🚧 In Progress (30-40% Remaining)

- 🚧 **Frontend UI** - React app scaffold complete, needs components
- 🚧 **Schema auto-execution** - DDL generated but requires manual approval
- 🚧 **Cluster naming** - Shows UUIDs instead of "Beach Photos" 
- 🚧 **Production hardening** - Authentication, multi-tenancy, rate limiting

## Key Technical Decisions

> See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed rationale

### Why CLIP for Media?
- **Zero-shot learning** - Works on any content without training
- **Semantic understanding** - Groups "sunset" with "beach" naturally
- **Text-to-image search** - Built-in multi-modal capability

### Why HDBSCAN for Clustering?
- **No manual K** - Discovers optimal number of clusters automatically
- **Handles outliers** - Doesn't force every image into a category
- **Hierarchical** - Can create sub-categories (e.g., "Black Cats" under "Cats")

### Why Hybrid SQL/JSONB?
- **Best of both worlds** - Structure where needed, flexibility elsewhere
- **Query performance** - Indexed SQL columns for filtering, JSONB for exploration
- **Schema evolution** - Add new fields without migrations

### Why PostgreSQL + pgvector?
- **Unified storage** - One database for everything (vectors, JSON, relations)
- **ACID transactions** - Critical for schema changes and migrations
- **Cost effective** - No separate vector database needed (Pinecone/Weaviate)

## Architecture Overview

```
                      ┌─────────────────┐
                      │   Frontend UI   │
                      │ (React + TS)    │
                      └────────┬────────┘
                               │
                      ┌────────▼────────┐
                      │   FastAPI       │
                      │  /api/v1/ingest │
                      └────────┬────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
         ┌──────────▼─────────┐  ┌───────▼────────┐
         │  Media Processor   │  │ JSON Processor │
         │  • CLIP embeddings │  │ • Schema score │
         │  • HDBSCAN cluster │  │ • DDL generate │
         │  • Directory org   │  │ • SQL/JSONB    │
         └──────────┬─────────┘  └───────┬────────┘
                    │                     │
                    └──────────┬──────────┘
                               │
                      ┌────────▼────────┐
                      │   PostgreSQL    │
                      │   + pgvector    │
                      │   + JSONB       │
                      └─────────────────┘
```

See [backend/docs/technical_specification.md](backend/docs/technical_specification.md) for implementation details.

## Quick Start

See [QUICKSTART.md](QUICKSTART.md) for detailed setup instructions.

### Backend Setup (Docker - Recommended)

```bash
cd backend

# One-time base image build (~30 minutes)
docker build -f Dockerfile.base -t mammothbox-base:latest .

# Fast app build (~2 seconds)
docker-compose build
docker-compose up -d

# Verify it's running
curl http://localhost:8000/health
```

**Performance:** After the one-time base image build, subsequent code changes rebuild in ~3 seconds! (1,350x speedup)

### Frontend Setup (Coming Soon)

```bash
cd frontend
npm install
npm run dev
```

## Development

### Backend Development

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
pytest
```

See [backend/README.md](backend/README.md) for backend-specific documentation.

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

## For Judges: What to Explore

### 1. **Documentation** (Start Here)
- 📖 **[ARCHITECTURE.md](ARCHITECTURE.md)** - Every design decision explained (why CLIP? why HDBSCAN? why PostgreSQL?)
- 🗺️ **[ROADMAP.md](ROADMAP.md)** - What's done, what's in progress, concrete plans for completion
- ⚡ **[QUICKSTART.md](QUICKSTART.md)** - Get it running in 5 minutes

### 2. **Test the API** (Hands-On)

```bash
# 1. Upload some images
curl -F "file=@beach.jpg" http://localhost:8000/api/v1/ingest
curl -F "file=@cat.jpg" http://localhost:8000/api/v1/ingest

# 2. Search semantically
curl "http://localhost:8000/api/v1/search?q=beach+sunset&limit=5"

# 3. Upload JSON
curl -F "file=@users.json" http://localhost:8000/api/v1/ingest

# 4. Check proposed schema
curl http://localhost:8000/api/v1/admin/schemas

# 5. View API docs
open http://localhost:8000/docs  # Interactive Swagger UI
```

### 3. **Code Quality** (Review)
- ✅ **89% test coverage** - See `backend/tests/`
- ✅ **Type hints everywhere** - Python 3.10+ with Pydantic
- ✅ **Clear separation** - Clean architecture (routes → services → database)
- ✅ **Performance tested** - Handles 100 concurrent uploads

### 4. **What Makes This Special**
1. **Intelligence** - Not just file storage, understands content semantically
2. **Adaptability** - Learns categories from data, doesn't require pre-configuration
3. **Unified** - One API for everything (vs separate upload/analyze/store steps)
4. **Production-ready foundations** - Docker, monitoring, testing, queue system

### 5. **Honest Assessment**
- ✅ **Core problem solved** - Media clustering ✅, JSON schema inference ✅
- 🚧 **UI in progress** - Backend complete, frontend scaffold done
- 📋 **Future work clearly defined** - See ROADMAP.md for concrete plans
- 💡 **Learned lessons documented** - ARCHITECTURE.md explains what we'd change

## Project Structure

```
backend/
├── src/
│   ├── api/              # HTTP API handlers
│   ├── ingest/           # Ingestion orchestrator
│   ├── media/            # Media processing (CLIP, clustering)
│   ├── catalog/          # Database models & queries
│   └── queue/            # Background job processing
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

</details>
