# Quick Start Guide

Get the Automated File Allocator running in 5 minutes (after one-time base image build).

## Prerequisites

- Docker & Docker Compose
- 4GB RAM minimum
- Internet connection (for base image build)

## First Time Setup

```bash
# Clone and navigate to project
cd MammothBox

# STEP 1: Build base image (ONE TIME, ~45 minutes)
# This downloads all dependencies and the ML model
docker build -f Dockerfile.base -t mammothbox-base:latest .

# Or use the script:
# PowerShell: .\build-base.ps1
# Bash: ./build-base.sh

# STEP 2: Build application (~5 seconds)
docker-compose build

# STEP 3: Start all services
docker-compose up -d

# Check if ready
curl http://localhost:8000/ready
# Response: {"status":"ready","database":"connected"}
```

## Subsequent Starts (After Base Image Built)

```bash
# For code changes, rebuild app (takes ~5 seconds)
docker-compose build app
docker-compose up -d

# Or just restart if no code changes
docker-compose up -d
```

## Test the API

### 1. Upload an Image

```bash
# Upload a test image
curl -X POST http://localhost:8000/api/v1/ingest \
  -F "files=@your_image.jpg" \
  -F "owner=test_user"

# Response includes job_id
# {"job_id":"abc-123","system_ids":["def-456"],"status":"accepted"}
```

### 2. Check Processing Status

```bash
curl http://localhost:8000/api/v1/ingest/<JOB_ID>/status

# Wait ~15 seconds, status should change:
# "queued" → "processing" → "done"
```

### 3. Search Your Images

```bash
# Semantic search (finds images matching text description)
curl "http://localhost:8000/api/v1/search?query=cat&limit=10"
curl "http://localhost:8000/api/v1/search?query=red+car&limit=5"
```

## What Happens Behind the Scenes

1. **Upload**: Image stored in `storage/incoming/`
2. **Processing** (~15 sec):
   - Generate CLIP embedding (512-dim vector)
   - Create thumbnail
   - Detect text with OCR (if applicable)
   - Cluster with similar images
3. **Storage**: Organized in `storage/media/<cluster_name>/`
4. **Search**: Vector similarity search using pgvector

## Services Running

- **API**: http://localhost:8000 (FastAPI)
- **Database**: PostgreSQL with pgvector extension
- **Redis**: Job queue (in-memory)

## Common Commands

```bash
# View logs
docker logs file_allocator_app --follow

# Rebuild after code changes (fast, ~5 seconds)
docker-compose build app
docker-compose up -d

# Restart services (no rebuild)
docker-compose restart

# Stop everything
docker-compose down

# Reset database (WARNING: deletes all data)
docker-compose down -v
docker-compose up -d

# Rebuild base image (only if requirements.txt changes)
docker build -f Dockerfile.base -t mammothbox-base:latest .
```

## Upload Multiple Files

```powershell
# PowerShell
$images = Get-ChildItem -Path "path\to\images" -Filter "*.jpg"
foreach($img in $images) {
    curl -X POST "http://localhost:8000/api/v1/ingest" -F "files=@$($img.FullName)"
}
```

```bash
# Bash
for img in /path/to/images/*.jpg; do
    curl -X POST "http://localhost:8000/api/v1/ingest" -F "files=@$img"
done
```

## Troubleshooting

**"mammothbox-base:latest not found" error?**

- You need to build the base image first: `docker build -f Dockerfile.base -t mammothbox-base:latest .`
- Or use the script: `.\build-base.ps1` (PowerShell) or `./build-base.sh` (Bash)

**Base image build takes 45 minutes?**

- This is normal! It's a one-time cost
- Downloads system packages, Python packages, and ML model (~990MB)
- After this, all rebuilds take ~5 seconds

**"Connection refused" errors?**

- Check containers: `docker-compose ps`
- View logs: `docker logs file_allocator_app`

**Search returns empty results?**

- Upload more images first (need at least 5-10 for meaningful results)
- Wait 15-20 seconds after upload for processing to complete

**Out of memory?**

- Reduce worker count in `src/config/settings.py`
- Close other applications

**Code changes not reflecting?**

- Rebuild app: `docker-compose build app && docker-compose up -d`
- Takes only ~5 seconds with base image approach

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       v
┌─────────────────────────────────────┐
│         FastAPI Server              │
│  ┌──────────┐      ┌─────────────┐ │
│  │ Ingest   │      │   Search    │ │
│  │ Endpoint │      │  Endpoint   │ │
│  └────┬─────┘      └──────┬──────┘ │
└───────┼───────────────────┼─────────┘
        │                   │
        v                   v
┌───────────────┐    ┌──────────────┐
│  Job Queue    │    │  PostgreSQL  │
│  (Redis)      │    │  + pgvector  │
└───────┬───────┘    └──────────────┘
        │
        v
┌──────────────────────┐
│  Media Processor     │
│  - CLIP embeddings   │
│  - Clustering        │
│  - OCR text extract  │
└──────────────────────┘
```

## Next Steps

- See [README.md](README.md) for full feature list
- Check [docs/API.md](docs/API.md) for complete API reference
- Review [docs/technical_specification.md](docs/technical_specification.md) for architecture details

## API Endpoints Summary

| Endpoint                         | Method | Purpose           |
| -------------------------------- | ------ | ----------------- |
| `/live`                          | GET    | Liveness check    |
| `/ready`                         | GET    | Readiness check   |
| `/api/v1/ingest`                 | POST   | Upload files/JSON |
| `/api/v1/ingest/{job_id}/status` | GET    | Check job status  |
| `/api/v1/search`                 | GET    | Semantic search   |
| `/api/v1/objects/{system_id}`    | GET    | Get asset details |

---

**System ready! Start uploading images and searching with natural language. 🚀**
