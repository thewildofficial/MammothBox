# Technical Specification Document
## Automated File Allocator - Python + FastAPI Implementation

**Version:** 1.0  
**Date:** 2024  
**Status:** Implementation Ready

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Technology Stack](#technology-stack)
3. [System Architecture](#system-architecture)
4. [API Endpoints Specification](#api-endpoints-specification)
5. [Media Processing Pipeline](#media-processing-pipeline)
6. [Document & Text Processing Pipeline](#document--text-processing-pipeline)
7. [JSON Processing Pipeline](#json-processing-pipeline)
8. [Search & Retrieval Pipeline](#search--retrieval-pipeline)
9. [Semantic Knowledge Organization](#semantic-knowledge-organization)
10. [Admin Operations Pipeline](#admin-operations-pipeline)
11. [Data Models & Database Schema](#data-models--database-schema)
12. [Storage Architecture](#storage-architecture)
13. [Error Handling & Resilience](#error-handling--resilience)
14. [Performance Targets](#performance-targets)

---

## Problem Statement

### Challenge
Design a smart storage system with a single frontend interface that intelligently processes and stores any type of data.

### Key Requirements

**For Media Files (Images/Videos):**
- Accept any media type through a unified frontend
- Automatically analyze and categorize content using CLIP embeddings
- Detect images that contain text and extract OCR content before semantic tagging
- Place files with related existing media in appropriate directories
- Create new directories for unique content categories
- Organize subsequent related media into existing directories
- Extract and index embedded images discovered inside container files (e.g., PDFs, EPUBs)

**For Textual & Document Assets:**
- Accept text-heavy formats (Markdown, PDF, EPUB, DOCX, PPTX, TXT, source code, etc.)
- Split documents into semantically meaningful chunks with preserved hierarchy
- Generate dense text embeddings for retrieval and cross-modal search
- Surface embedded media (images, audio snippets) for downstream pipelines
- Support recursive folder ingestion to process large corpora consistently

**For Audio Assets:**
- Accept raw audio uploads alongside other media
- Detect whether files contain linguistic content or non-speech signals
- Transcribe speech with streaming-capable models and generate text embeddings
- Produce spectrogram embeddings for music or ambient audio when no speech is present
- Categorize audio by genre, speaker, or acoustic profile for downstream search

**For Structured Data (JSON Objects):**
- Accept JSON objects through the same frontend
- Intelligently determine whether SQL or NoSQL (JSONB) is more appropriate
- Create the appropriate database entity automatically
- For multiple JSON objects: analyze structure and generate complete schema with proper relationships

**Additional Considerations:**
- System should accept optional comments/metadata to aid in schema generation
- Must handle both single and batch data inputs
- Should maintain consistency and optimize for query performance
- Human-in-the-loop: provisional decisions require admin approval
- Critical enhancements must prioritize semantic search coverage (text + media), and automated knowledge organization
- Future enhancements include full recursive folder ingestion and advanced audio heuristics

---

## Technology Stack

### Core Framework
- **FastAPI 0.104.1**: Modern, fast web framework for building APIs
- **Python 3.10+**: Primary programming language
- **Uvicorn**: ASGI server for FastAPI
- **Pydantic 2.5.0**: Data validation and settings management

### Database & Vector Search
- **PostgreSQL 14+**: Primary relational database
- **pgvector 0.2.4**: Vector similarity search extension
- **SQLAlchemy 2.0.23**: ORM for database operations
- **Alembic 1.12.1**: Database migration management
- **psycopg2-binary 2.9.9**: PostgreSQL adapter

### Machine Learning & Embeddings
- **sentence-transformers 2.2.2**: CLIP model wrapper (CPU-friendly)
- **transformers 4.35.2**: Hugging Face transformers library
- **torch 2.1.1**: PyTorch for tensor operations
- **onnxruntime 1.16.3**: ONNX runtime for optimized inference
- **Model**: `clip-ViT-B-32` (512-dimensional embeddings, CPU-optimized)

### Text & Document Embeddings
- **sentence-transformers 2.2.2**: Long-form text encoders (`all-MiniLM-L12-v2`, `gte-base`)
- **langchain-text-splitters 0.1.x**: Structure-aware chunking for documents and code
- **unstructured 0.12.x**: Multi-format document parsing (PDF, EPUB, PPTX, DOCX, HTML)
- **rapidfuzz 3.6.x**: Fuzzy matching for de-duplication and content linking

### Vision Language Model (VLM)
- **google-generativeai**: Google Generative AI SDK for Gemini API
- **Model**: `gemini-2.5-flash` or `gemini-2.5-flash-lite` (for image analysis and metadata extraction)
- **Purpose**: Dynamic tag generation, scene understanding, and rich metadata extraction

### Media Processing
- **Pillow 10.1.0**: Image processing and normalization
- **opencv-python-headless 4.8.1.78**: Video processing and keyframe extraction
- **imagehash 4.3.1**: Perceptual hashing for deduplication
- **ffmpeg-python 0.2.0**: Video transcoding and keyframe extraction
- **pytesseract 0.3.10**: OCR for text-in-image detection
- **pdfminer.six 20231228**: Embedded image extraction from PDFs
- **python-docx 1.0.x / python-pptx 0.6.x**: Office document parsing

### Storage
- **boto3 1.29.7**: AWS S3 SDK (for production S3 backend)
- **Local Filesystem**: Default storage backend (`fs://`)

### Job Queue & Async Processing
- **redis 5.0.1**: Optional Redis backend for distributed queues
- **In-process Queue**: Default for MVP (Python `queue.Queue`)

### Utilities
- **python-multipart 0.0.6**: Multipart form data handling
- **python-dotenv 1.0.0**: Environment variable management
- **httpx 0.25.2**: HTTP client for external API calls
- **anytree 2.12.1**: LLM-driven hierarchy construction and traversal
- **networkx 3.2.1**: Graph analytics for similarity tree evaluation

### Speech & Audio Analysis
- **faster-whisper 0.10.x**: Low-latency speech-to-text transcription
- **librosa 0.10.1**: Audio feature extraction and genre detection
- **pydub 0.25.1**: Audio normalization and segment handling

### Testing & Development
- **pytest 7.4.3**: Testing framework
- **pytest-asyncio 0.21.1**: Async test support
- **pytest-cov 4.1.0**: Code coverage
- **black 23.11.0**: Code formatting
- **flake8 6.1.0**: Linting
- **mypy 1.7.1**: Type checking

### Deployment
- **Docker & Docker Compose**: Containerization
- **PostgreSQL with pgvector**: Database container
- **Redis**: Optional queue backend container

---

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Layer                             │
│  (CLI tools, SDKs, Web UI, Admin Dashboard)                │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│              FastAPI HTTP API Layer                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  POST /api/v1/ingest                                 │  │
│  │  GET  /api/v1/ingest/{job_id}/status                 │  │
│  │  GET  /api/v1/objects/{system_id}                    │  │
│  │  GET  /api/v1/search                                 │  │
│  │  PATCH /api/v1/clusters/{cluster_id}                 │  │
│  │  GET  /api/v1/schemas                                │  │
│  │  POST /api/v1/schemas/{schema_id}/approve            │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│            Ingest Orchestrator                              │
│  - Request validation                                       │
│  - Raw storage persistence                                  │
│  - Job enqueueing                                           │
│  - Lineage tracking                                         │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┬────────────┬────────────┐
        │            │            │            │
┌───────▼────────┐┌──▼──────────┐┌────────────▼──────────┐
│  Media         ││  JSON       ││  Document & Text      │
│  Processor     ││  Processor  ││  Processor            │
│                ││             ││                       │
│  - Normalize   ││  - Flatten  ││  - Parse & Chunk      │
│  - Embed       ││  - Analyze  ││  - Embed & Summarize  │
│  - Cluster     ││  - Schema   ││  - Embedded Media     │
│  - Dedupe      ││    Decider  ││    Extraction         │
└───────┬────────┘└─────────────┘└────────────┬──────────┘
        │                                     │
        └────────────┬────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│      Knowledge Graph & Semantic Tree Builder                │
│  - Similarity graph construction                            │
│  - Hierarchical LLM routing                                 │
│  - Guardrail enforcement                                    │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│         PostgreSQL + pgvector                               │
│  - asset_raw (immutable)                                    │
│  - asset (metadata, embeddings)                             │
│  - cluster (centroids, thresholds)                          │
│  - schema_def (proposals, DDL)                              │
│  - lineage (audit trail)                                    │
│  - video_frame (per-frame embeddings)                        │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│         Storage Adapter (fs:// or s3://)                    │
│  - incoming/{request_id}/{part_id}                          │
│  - media/clusters/{cluster_id}/{asset_id}                   │
│  - media/derived/{cluster_id}/{asset_id}/                   │
└─────────────────────────────────────────────────────────────┘
```

### Module Organization

```
src/
├── api/              # FastAPI route handlers
│   └── routes.py     # All endpoint definitions
├── ingest/           # Ingestion orchestrator
│   ├── __init__.py
│   ├── orchestrator.py
│   └── validator.py
├── media/            # Media processing pipeline
│   ├── __init__.py
│   ├── processor.py
│   ├── embedder.py
│   ├── clusterer.py
│   └── deduplicator.py
├── documents/        # Text & document processing pipeline
│   ├── __init__.py
│   ├── processor.py
│   ├── chunker.py
│   ├── embedder.py
│   └── ocr.py
├── json/             # JSON processing pipeline
│   ├── __init__.py
│   ├── processor.py
│   ├── schema_decider.py
│   └── ddl_generator.py
├── knowledge/        # Semantic hierarchy builder
│   ├── __init__.py
│   ├── organizer.py
│   ├── guardrails.py
│   └── tree_models.py
├── catalog/          # Metadata catalog service
│   ├── __init__.py
│   ├── models.py      # SQLAlchemy models
│   └── queries.py     # Complex queries
├── storage/          # Storage abstraction
│   ├── __init__.py
│   ├── adapter.py
│   ├── filesystem.py
│   └── s3.py
├── queue/            # Job queue interface
│   ├── __init__.py
│   ├── interface.py
│   ├── inproc.py
│   └── redis.py
├── admin/            # Admin UI backend
│   ├── __init__.py
│   └── handlers.py
├── config/           # Configuration management
│   ├── __init__.py
│   └── settings.py
└── main.py           # Application entry point
```

---

## API Endpoints Specification

### Base URL
```
http://localhost:8000/api/v1
```

### Authentication
Currently: None (for MVP)  
Future: API key or JWT token authentication

---

### 1. POST /api/v1/ingest

**Purpose:** Unified ingestion endpoint for media files and JSON documents.

**Request:**
- **Content-Type:** `multipart/form-data` or `application/json`
- **Method:** POST

**Form Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `files[]` | File[] | No* | Media files (images, videos, audio). Required if `payload` not provided |
| `payload` | String (JSON) | No* | JSON object or array. Required if `files[]` not provided |
| `folder_uri` | String (URI) | No | Remote/local URI to a folder/archive to ingest recursively (future enhancement behind feature flag) |
| `owner` | String | No | Owner identifier for tracking |
| `comments` | String | No | Optional metadata/comments to aid processing |
| `idempotency_key` | String | No | Idempotency key for deduplication |

**Request Examples:**

```bash
# Media files only
curl -X POST http://localhost:8000/api/v1/ingest \
  -F "files[]=@image1.jpg" \
  -F "files[]=@video1.mp4" \
  -F "owner=user123" \
  -F "comments=Vacation photos"

# JSON payload only
curl -X POST http://localhost:8000/api/v1/ingest \
  -F "payload={\"name\":\"John\",\"age\":30,\"city\":\"NYC\"}" \
  -F "owner=user123"

# Mixed (media + JSON)
curl -X POST http://localhost:8000/api/v1/ingest \
  -F "files[]=@photo.jpg" \
  -F "payload={\"description\":\"Beach sunset\"}" \
  -F "owner=user123"

# Batch JSON (array)
curl -X POST http://localhost:8000/api/v1/ingest \
  -F "payload=[{\"name\":\"Alice\"},{\"name\":\"Bob\"}]" \
  -F "owner=user123"
```

**Response:**
- **Status Code:** `202 Accepted`
- **Content-Type:** `application/json`

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "system_ids": [
    "asset-uuid-1",
    "asset-uuid-2"
  ],
  "status": "accepted",
  "request_id": "req-12345",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Response Fields:**
- `job_id` (UUID): Unique job identifier for tracking
- `system_ids` (UUID[]): One per logical object ingested
- `status` (String): Always "accepted" for 202 response
- `request_id` (String): Request tracking identifier
- `created_at` (ISO8601): Timestamp of ingestion

**Error Responses:**

| Status Code | Description | Response Body |
|-------------|-------------|---------------|
| 400 | Invalid request (no files or payload) | `{"error": "Either files[] or payload must be provided"}` |
| 400 | Invalid JSON payload | `{"error": "Invalid JSON format", "details": "..."}` |
| 413 | Payload too large | `{"error": "Payload exceeds maximum size limit"}` |
| 409 | Duplicate (idempotency key) | `{"error": "Duplicate request", "existing_job_id": "..."}` |
| 500 | Internal server error | `{"error": "Internal server error", "request_id": "..."}` |

**Processing Flow:**
1. Validate request (files or payload present)
2. Generate `request_id` and `job_id`
3. (Optional) If `folder_uri` provided: enumerate files recursively, respecting ignore patterns, and enqueue each asset as a child job
4. Store raw bytes to `storage/incoming/{request_id}/{part_id}`
5. Create `asset_raw` records in database
6. Create `lineage` audit records
7. Enqueue processing jobs (one per logical object or document chunk)
8. Return 202 with job_id immediately

---

### 2. GET /api/v1/ingest/{job_id}/status

**Purpose:** Check processing status for an ingestion job.

**Request:**
- **Method:** GET
- **Path Parameter:** `job_id` (UUID)

**Example:**
```bash
curl http://localhost:8000/api/v1/ingest/550e8400-e29b-41d4-a716-446655440000/status
```

**Response:**
- **Status Code:** `200 OK`
- **Content-Type:** `application/json`

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "progress": {
    "queued": 0,
    "processing": 1,
    "done": 2,
    "failed": 0,
    "total": 3
  },
  "assets": [
    {
      "system_id": "asset-uuid-1",
      "status": "done",
      "cluster_id": "cluster-uuid-1",
      "schema_id": null
    },
    {
      "system_id": "asset-uuid-2",
      "status": "processing",
      "cluster_id": null,
      "schema_id": null
    }
  ],
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:05Z"
}
```

**Response Fields:**
- `job_id` (UUID): Job identifier
- `status` (String): Overall job status: `queued`, `processing`, `done`, `failed`, `partial`
- `progress` (Object): Counts by status
- `assets` (Array): Per-asset status details
- `created_at` (ISO8601): Job creation timestamp
- `updated_at` (ISO8601): Last update timestamp

**Error Responses:**

| Status Code | Description |
|-------------|-------------|
| 404 | Job not found |

---

### 3. GET /api/v1/objects/{system_id}

**Purpose:** Get canonical metadata for an asset by system ID.

**Request:**
- **Method:** GET
- **Path Parameter:** `system_id` (UUID)

**Example:**
```bash
curl http://localhost:8000/api/v1/objects/asset-uuid-1
```

**Response:**
- **Status Code:** `200 OK`

**For Media Assets:**
```json
{
  "id": "asset-uuid-1",
  "kind": "media",
  "uri": "media/clusters/cluster-uuid-1/asset-uuid-1.jpg",
  "content_type": "image/jpeg",
  "size_bytes": 245678,
  "sha256": "abc123...",
  "owner": "user123",
  "created_at": "2024-01-15T10:30:00Z",
  "status": "done",
  "cluster": {
    "id": "cluster-uuid-1",
    "name": "Cats",
    "provisional": false
  },
  "tags": ["cat", "black cat", "indoor", "pet", "feline", "close-up", "yellow eyes"],
  "embedding": {
    "dimension": 512,
    "model": "clip-ViT-B-32"
  },
  "metadata": {
    "width": 1920,
    "height": 1080,
    "exif": {...},
    "primary_category": "animals",
    "description": "A close-up portrait of a sleek black domestic cat with striking yellow eyes",
    "detected_objects": ["cat", "carpet", "window"],
    "scene_type": "portrait",
    "color_palette": ["black", "brown", "yellow", "beige"],
    "vlm_model": "gemini-2.5-flash"
  }
}
```

**For JSON Assets:**
```json
{
  "id": "asset-uuid-2",
  "kind": "json",
  "uri": null,
  "content_type": "application/json",
  "size_bytes": 1024,
  "sha256": "def456...",
  "owner": "user123",
  "created_at": "2024-01-15T10:30:00Z",
  "status": "done",
  "schema": {
    "id": "schema-uuid-1",
    "name": "user_profiles",
    "storage_choice": "sql",
    "status": "provisional",
    "ddl": "CREATE TABLE user_profiles (...)"
  },
  "storage_location": "user_profiles",
  "storage_id": "record-uuid-1"
}
```

**Error Responses:**

| Status Code | Description |
|-------------|-------------|
| 404 | Asset not found |

---

### 4. GET /api/v1/search

**Purpose:** Semantic search for media files using CLIP embeddings.

**Request:**
- **Method:** GET
- **Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | String | Yes | - | Search query text |
| `type` | String | No | `media` | Filter by type: `media` or `json` |
| `limit` | Integer | No | 10 | Maximum results (1-100) |
| `threshold` | Float | No | 0.5 | Minimum similarity score (0.0-1.0) |
| `owner` | String | No | - | Filter by owner |
| `cluster_id` | UUID | No | - | Filter by cluster |
| `tags` | String[] | No | - | Filter by tags (comma-separated) |

**Example:**
```bash
curl "http://localhost:8000/api/v1/search?query=dog&type=media&limit=10&threshold=0.7"
```

**Response:**
- **Status Code:** `200 OK`

```json
{
  "query": "dog",
  "results": [
    {
      "id": "asset-uuid-1",
      "kind": "media",
      "uri": "media/clusters/cluster-uuid-1/asset-uuid-1.jpg",
      "similarity": 0.92,
      "tags": ["dog", "pet", "animal", "canine"],
      "cluster": {
        "id": "cluster-uuid-1",
        "name": "Dogs"
      },
      "thumbnail": "media/derived/cluster-uuid-1/asset-uuid-1/thumb.jpg"
    },
    {
      "id": "asset-uuid-2",
      "kind": "media",
      "uri": "media/clusters/cluster-uuid-1/asset-uuid-2.jpg",
      "similarity": 0.87,
      "tags": ["dog", "golden retriever"],
      "cluster": {
        "id": "cluster-uuid-1",
        "name": "Dogs"
      },
      "thumbnail": "media/derived/cluster-uuid-1/asset-uuid-2/thumb.jpg"
    }
  ],
  "total": 2,
  "query_time_ms": 45
}
```

**Search Pipeline:**
1. Encode query text using CLIP text encoder
2. Perform ANN search in pgvector (cosine similarity)
3. Apply filters (type, owner, cluster, tags)
4. Sort by similarity score
5. Return top-K results

---

### 5. PATCH /api/v1/clusters/{cluster_id}

**Purpose:** Admin operations on clusters (rename, merge, adjust thresholds).

**Request:**
- **Method:** PATCH
- **Path Parameter:** `cluster_id` (UUID)
- **Content-Type:** `application/json`

**Request Body:**
```json
{
  "action": "rename",
  "name": "Updated Cluster Name"
}
```

**Actions:**

**Rename Cluster:**
```json
{
  "action": "rename",
  "name": "New Cluster Name"
}
```

**Merge Clusters:**
```json
{
  "action": "merge",
  "source_cluster_ids": ["cluster-uuid-2", "cluster-uuid-3"]
}
```

**Adjust Threshold:**
```json
{
  "action": "update_threshold",
  "threshold": 0.75
}
```

**Mark Provisional/Confirmed:**
```json
{
  "action": "confirm",
  "provisional": false
}
```

**Response:**
- **Status Code:** `200 OK`

```json
{
  "cluster_id": "cluster-uuid-1",
  "action": "rename",
  "status": "success",
  "updated_at": "2024-01-15T10:35:00Z"
}
```

**Error Responses:**

| Status Code | Description |
|-------------|-------------|
| 404 | Cluster not found |
| 400 | Invalid action or parameters |
| 409 | Merge conflict (clusters have incompatible types) |

---

### 6. GET /api/v1/schemas

**Purpose:** List all schema proposals (for admin review).

**Request:**
- **Method:** GET
- **Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `status` | String | No | - | Filter by status: `provisional`, `active`, `rejected` |
| `storage_choice` | String | No | - | Filter by storage: `sql`, `jsonb` |

**Example:**
```bash
curl "http://localhost:8000/api/v1/schemas?status=provisional"
```

**Response:**
```json
{
  "schemas": [
    {
      "id": "schema-uuid-1",
      "name": "user_profiles",
      "storage_choice": "sql",
      "status": "provisional",
      "version": 1,
      "structure_hash": "abc123...",
      "ddl": "CREATE TABLE user_profiles (...)",
      "sample_count": 50,
      "created_at": "2024-01-15T10:30:00Z",
      "assets_count": 50
    }
  ],
  "total": 1
}
```

---

### 7. POST /api/v1/schemas/{schema_id}/approve

**Purpose:** Approve a provisional schema proposal (admin action).

**Request:**
- **Method:** POST
- **Path Parameter:** `schema_id` (UUID)
- **Body:** (optional modifications)

```json
{
  "auto_migrate": true,
  "modifications": {
    "table_name": "custom_user_profiles"
  }
}
```

**Response:**
```json
{
  "schema_id": "schema-uuid-1",
  "status": "active",
  "migration_applied": true,
  "migration_id": "migration-uuid-1",
  "updated_at": "2024-01-15T10:40:00Z"
}
```

---

### 8. GET /live

**Purpose:** Liveness health check.

**Response:**
```json
{
  "status": "alive"
}
```

---

### 9. GET /ready

**Purpose:** Readiness health check (checks database connectivity).

**Response:**
```json
{
  "status": "ready",
  "database": "connected",
  "storage": "available"
}
```

---

## Media Processing Pipeline

### Overview
The media processing pipeline handles images, videos, and audio files. It performs normalization, embedding generation, clustering, and deduplication.

### Pipeline Stages

#### Stage 1: Classification & Validation
**Module:** `src/ingest/validator.py`

**Input:** Raw file bytes from `asset_raw`

**Process:**
1. Detect MIME type from content (magic bytes)
2. Validate file extension matches content
3. Check file size limits:
   - Images: max 50MB
   - Videos: max 500MB
   - Audio: max 100MB
4. Extract basic metadata (dimensions, duration, codec)

**Output:** `MediaMetadata` object with:
- `content_type`: MIME type
- `file_size`: Size in bytes
- `width`, `height`: For images/videos
- `duration`: For videos/audio
- `codec`: For videos/audio

**Technology:**
- `python-magic` or `filetype` for MIveME detection
- `Pillow` for image metadata
- `ffprobe` (via `ffmpeg-python`) for video metadata

---

#### Stage 2: Normalization & Preprocessing
**Module:** `src/media/processor.py`

**Images:**
1. Convert to RGB color space
2. Resize to max dimension 1024px (maintain aspect ratio)
3. Generate thumbnail (256x256)
4. Extract EXIF metadata
5. Compute perceptual hash (`pHash`) for deduplication
6. Run adaptive text-detection heuristic (edge density + OCR confidence scoring)
7. If text detected above threshold:
   - Extract OCR text with `pytesseract`
   - Generate bounding box metadata for overlay rendering
   - Emit derived text chunk for cross-modal search

**Videos:**
1. Extract keyframes using scene detection:
   - Extract up to `N_keyframes = min(3, duration_seconds/10)`
   - Use `ffmpeg` scene detection (`-vf "select='gt(scene,0.3)'"`)
2. Generate thumbnail from first keyframe
3. Extract metadata (resolution, codec, bitrate, duration)
4. **VLM Analysis**: Analyze keyframes with Gemini (if enabled)
   - Analyze each keyframe separately
   - Aggregate tags and metadata across keyframes
   - Use most representative keyframe for cluster naming
5. Detect text overlays per keyframe; route positive frames to OCR pipeline

**Audio:**
1. Extract metadata (duration, bitrate, codec, sample rate)
2. Run lightweight VAD + language detection to decide speech vs non-speech
3. Generate waveform visualization (optional)
4. Segment long recordings into logical chapters for transcription

**Output:** Normalized media files stored in `storage/incoming/{request_id}/normalized/`

**Technology:**
- `Pillow` for image processing
- `opencv-python-headless` for video processing
- `ffmpeg-python` for video keyframe extraction
- `imagehash` for perceptual hashing

---

#### Stage 3: Embedding Generation
**Module:** `src/media/embedder.py`

**Process:**
1. Load CLIP model (`clip-ViT-B-32`) on worker startup (cached)
2. For images:
   - Encode image using CLIP image encoder
   - Output: 512-dimensional normalized vector
3. For videos:
   - Encode each keyframe separately
   - Mean-pool keyframe embeddings → single 512-d vector
   - Store individual keyframe embeddings in `video_frame` table
4. For audio:
   - If speech detected:
     - Transcribe with `faster-whisper` (streaming friendly)
     - Chunk transcript sentences and embed with text encoder (768-d)
     - Generate speaker diarization metadata when available
   - If no speech detected:
     - classify based
   - Output: paired audio + transcript embeddings

**Performance Targets:**
- Image encoding: < 250ms per image (CPU)
- Video encoding: < 1s per keyframe
- Batch processing: 16 images per batch

**Output:**
- `embedding`: 512-d vector (stored in `asset.embedding`)
- `text_embedding`: 768-d vector (stored in `asset.text_embedding` when applicable)
- `video_frame` records (for videos)
- `audio_segment` records (for segmented speech/music)

**Technology:**
- `sentence-transformers` with `clip-ViT-B-32`
- `torch` for tensor operations
- `onnxruntime` (optional) for optimized inference

**Code Example:**
```python
from sentence_transformers import SentenceTransformer
import torch

model = SentenceTransformer("clip-ViT-B-32", device="cpu")

# Image embedding
image_embedding = model.encode(
    image,
    batch_size=16,
    convert_to_tensor=True,
    normalize_embeddings=True
)

# Text embedding (for search)
text_embedding = model.encode(
    query_text,
    convert_to_tensor=True,
    normalize_embeddings=True
)
```

---

#### Stage 4: VLM-Based Metadata Extraction & Tag Generation
**Module:** `src/media/vlm_analyzer.py`

**Purpose:** Use Gemini 2.5 Flash to analyze images and extract rich, contextual metadata without predefined categories.

**Process:**
1. **Prepare Image:**
   - Use normalized image from Stage 2 (max 1024px)
   - Convert to base64 or PIL Image format for API

2. **Call Gemini 2.5 Flash API:**
   - Model: `gemini-2.5-flash` or `gemini-2.5-flash-lite`
   - Use structured output with JSON schema
   - Request comprehensive image analysis

3. **Extract Structured Metadata:**
   - Parse JSON response from VLM
   - Extract tags, categories, descriptions, and metadata

4. **Fallback Strategy:**
   - If API fails or times out: fall back to CLIP zero-shot with basic categories
   - Log fallback for monitoring

**VLM Prompt Design:**
```python
PROMPT_TEMPLATE = """
Analyze this image and provide structured metadata in JSON format.

Extract the following information:
1. **Primary Category**: The main subject/category (e.g., "animals", "vehicles", "food", "nature", "people", "architecture", "technology", "art", "sports", "fashion", etc.)

2. **Tags**: Array of 5-15 descriptive tags covering:
   - Main subjects/objects (e.g., "cat", "mountain", "car")
   - Scene/context (e.g., "outdoor", "indoor", "sunset", "beach")
   - Activities/actions (e.g., "running", "cooking", "playing")
   - Attributes (e.g., "red", "vintage", "modern", "close-up")
   - Mood/atmosphere (e.g., "peaceful", "energetic", "dramatic")

3. **Description**: A concise 1-2 sentence description of the image

4. **Detected Objects**: Array of specific objects found (with confidence)

5. **Scene Type**: Type of scene (e.g., "portrait", "landscape", "still life", "action", "abstract")

6. **Color Palette**: Dominant colors (3-5 colors)

7. **Suggested Cluster Name**: A human-readable name for grouping similar images (e.g., "Golden Retrievers", "Mountain Landscapes", "Red Sports Cars")

Return ONLY valid JSON in this exact structure:
{{
    "primary_category": "string",
    "tags": ["tag1", "tag2", ...],
    "description": "string",
    "detected_objects": ["object1", "object2", ...],
    "scene_type": "string",
    "color_palette": ["color1", "color2", ...],
    "suggested_cluster_name": "string"
}}
"""

# Use Gemini's structured output feature
response = model.generate_content(
    [PROMPT_TEMPLATE, image],
    generation_config={
        "response_mime_type": "application/json",
        "response_schema": {
            "type": "object",
            "properties": {
                "primary_category": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "description": {"type": "string"},
                "detected_objects": {"type": "array", "items": {"type": "string"}},
                "scene_type": {"type": "string"},
                "color_palette": {"type": "array", "items": {"type": "string"}},
                "suggested_cluster_name": {"type": "string"}
            },
            "required": ["primary_category", "tags", "description", "suggested_cluster_name"]
        }
    }
)
```

**Output Structure:**
```python
{
    "primary_category": "animals",
    "tags": ["cat", "black cat", "indoor", "pet", "feline", "close-up", "yellow eyes", "domestic cat"],
    "description": "A close-up portrait of a sleek black domestic cat with striking yellow eyes, photographed indoors.",
    "detected_objects": ["cat", "carpet", "window"],
    "scene_type": "portrait",
    "color_palette": ["black", "brown", "yellow", "beige"],
    "suggested_cluster_name": "Black Cats"
}
```

**Storage:**
- `tags`: Stored in `asset.tags` array (used for filtering and search)
- `primary_category`: Stored in `asset.metadata->>'primary_category'`
- `description`: Stored in `asset.metadata->>'description'`
- `detected_objects`: Stored in `asset.metadata->>'detected_objects'`
- `scene_type`: Stored in `asset.metadata->>'scene_type'`
- `color_palette`: Stored in `asset.metadata->>'color_palette'`
- `suggested_cluster_name`: Used for cluster naming (Stage 6)

**Performance Targets:**
- VLM API call: < 2s per image (Gemini Flash is fast)
- Fallback to CLIP: < 500ms per image
- Batch processing: Sequential (API rate limits apply)

**Technology:**
- `google-generativeai`: Google Generative AI SDK
- `Pillow`: Image preprocessing
- `httpx`: HTTP client for API calls (if not using SDK)

**Code Example:**
```python
import google.generativeai as genai
from PIL import Image
import json

# Initialize Gemini client
genai.configure(api_key=settings.gemini_api_key)
model = genai.GenerativeModel('gemini-2.5-flash')
def analyze_image_vlm(image: Image.Image) -> dict:
    """Analyze image using Gemini VLM and return structured metadata."""
    try:
        # Prepare prompt
        prompt = PROMPT_TEMPLATE
        
        # Call API with structured output
        response = model.generate_content(
            [prompt, image],
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.3,  # Lower temperature for more consistent output
            }
        )
        
        # Parse JSON response
        metadata = json.loads(response.text)
        
        # Validate and normalize
        tags = metadata.get("tags", [])
        if not tags:
            tags = [metadata.get("primary_category", "unknown")]
        
        return {
            "tags": tags[:15],  # Limit to 15 tags
            "primary_category": metadata.get("primary_category", "unknown"),
            "description": metadata.get("description", ""),
            "detected_objects": metadata.get("detected_objects", []),
            "scene_type": metadata.get("scene_type", ""),
            "color_palette": metadata.get("color_palette", []),
            "suggested_cluster_name": metadata.get("suggested_cluster_name", "Uncategorized"),
            "vlm_model": "gemini-2.5-flash"
        }
    except Exception as e:
        # Fallback to CLIP zero-shot
        logger.warning(f"VLM analysis failed: {e}, falling back to CLIP")
        return fallback_clip_tags(image)
```

**Fallback Implementation:**
```python
def fallback_clip_tags(image: Image.Image) -> dict:
    """Fallback to CLIP zero-shot if VLM fails."""
    # Basic categories for fallback
    basic_categories = [
        "animal", "person", "vehicle", "food", "nature", "building",
        "object", "text", "abstract", "indoor", "outdoor"
    ]
    
    # Encode image and categories
    image_embedding = clip_model.encode(image, normalize_embeddings=True)
    category_embeddings = clip_model.encode(basic_categories, normalize_embeddings=True)
    
    # Find best matches
    similarities = cosine_similarity(image_embedding, category_embeddings)
    top_indices = similarities.argsort()[-3:][::-1]
    tags = [basic_categories[i] for i in top_indices if similarities[i] > 0.3]
    
    return {
        "tags": tags or ["unknown"],
        "primary_category": tags[0] if tags else "unknown",
        "description": "",
        "suggested_cluster_name": tags[0].title() if tags else "Uncategorized",
        "vlm_model": "clip-fallback"
    }
```

**Benefits of VLM Approach:**
1. **No Predefined Categories**: Adapts to any image type automatically
2. **Rich Context**: Understands scenes, activities, and relationships
3. **Better Clustering**: `suggested_cluster_name` provides semantic grouping hints
4. **Structured Metadata**: Enables advanced filtering and search
5. **Future-Proof**: Can handle new image types without code changes

**Cost Considerations:**

Input tokens (text, image, video): $0.30 per 1 million tokens

Audio input tokens: $1.00 per 1 million tokens

Text output tokens (response and reasoning): $2.50 per 1 million tokens

Image output tokens: $30.00 per 1 million tokens


**Rate Limits:**
- Default: 15 requests per minute (RPM)
- Can request higher limits from Google
- Implement exponential backoff for rate limit errors

---

#### Stage 5: Deduplication
**Module:** `src/media/deduplicator.py`

**Process:**
1. Compute SHA256 hash of raw file
2. Query database for existing assets with same SHA256
3. If exact duplicate found:
   - Link to existing asset (don't store duplicate file)
   - Mark as duplicate in `asset` record
   - Return existing `cluster_id`
4. If no exact duplicate:
   - Compute perceptual hash (`pHash`)
   - Query for similar perceptual hashes (Hamming distance < 5)
   - If near-duplicate found:
     - Optionally link or create new asset (configurable)
   - If no near-duplicate:
     - Proceed to clustering

**Output:** `is_duplicate` flag, `duplicate_of` reference (if applicable)

**Technology:**
- `hashlib` for SHA256
- `imagehash` for perceptual hashing

---

#### Stage 6: Cluster Assignment
**Module:** `src/media/clusterer.py`

**Process:**
1. Query all existing clusters from database
2. For each cluster:
   - Load centroid vector (`cluster.centroid`)
   - Compute cosine similarity: `cosine_sim = dot(embedding, centroid)`
3. Find cluster with highest similarity
4. If `max_similarity >= cluster.threshold`:
   - Assign asset to existing cluster
   - Update cluster centroid: `new_centroid = normalize(mean([old_centroid, embedding]))`
   - Update `cluster.updated_at`
5. Else (no cluster meets threshold):
   - Create new cluster:
     - `cluster.id` = new UUID
     - `cluster.name` = use `suggested_cluster_name` from VLM (e.g., "Black Cats", "Mountain Landscapes")
       - Fallback: generate from top tags if VLM not available
     - `cluster.centroid` = embedding
     - `cluster.threshold` = default (0.72)
     - `cluster.provisional` = true
   - Assign asset to new cluster

**Default Threshold:** 0.72 (cosine similarity)
- Lower threshold (0.70): Broader semantic grouping
- Higher threshold (0.80): Stricter visual similarity

**Output:** `cluster_id` assigned to asset

**Technology:**
- `pgvector` for ANN search (optional optimization)
- PostgreSQL `vector` type for storage

**VLM Integration with Clustering:**
- When creating a new cluster, use `suggested_cluster_name` from VLM analysis
- This provides human-readable, semantically meaningful cluster names
- Example: Instead of "Cluster 42", use "Black Cats" or "Mountain Landscapes"
- If VLM not available, fallback to generating name from top tags

**Code Example:**
```python
# ANN search in pgvector
query = """
SELECT id, centroid, threshold, name
FROM cluster
WHERE provisional = false
ORDER BY centroid <=> %s::vector
LIMIT 1
"""
result = db.execute(query, [embedding.tolist()])
if result and result.similarity >= result.threshold:
    assign_to_cluster(result.id, embedding)
else:
    # Use VLM suggested_cluster_name if available
    cluster_name = vlm_metadata.get("suggested_cluster_name") or generate_name_from_tags(tags)
    create_new_cluster(embedding, tags, cluster_name)
```

---

#### Stage 7: Final Storage
**Module:** `src/storage/adapter.py`

**Process:**
1. Move file from `storage/incoming/{request_id}/{part_id}` to:
   - `storage/media/clusters/{cluster_id}/{asset_id}.{ext}`
2. Store thumbnail in:
   - `storage/media/derived/{cluster_id}/{asset_id}/thumb.jpg`
3. Update `asset` record:
   - `uri` = final storage path
   - `status` = "done"
   - `cluster_id` = assigned cluster
   - `embedding` = vector
   - `tags` = array
4. Update `lineage` with completion status

**Output:** Asset fully processed and stored

---

### Media Processing Flow Diagram

```
Raw File Bytes
    ↓
[Classification & Validation]
    ↓
[Normalization & Preprocessing]
    ├─→ Images: Resize, thumbnail, EXIF
    ├─→ Videos: Keyframes, thumbnail
    └─→ Audio: Metadata, waveform
    ↓
[Embedding Generation]
    ├─→ CLIP Image Encoder → 512-d vector
    └─→ (Videos: Mean-pool keyframe embeddings)
    ↓
[VLM Metadata Extraction]
    ├─→ Gemini 2.5 Flash API → structured metadata
    ├─→ Extract tags, categories, description
    └─→ Fallback to CLIP if API fails
    ↓
[Deduplication]
    ├─→ SHA256 check → exact duplicate?
    └─→ pHash check → near-duplicate?
    ↓
[Cluster Assignment]
    ├─→ ANN search → find nearest cluster
    ├─→ Similarity >= threshold? → assign
    └─→ Else → create new cluster
    ↓
[Final Storage]
    ├─→ Move to cluster directory
    ├─→ Store thumbnail
    └─→ Update asset record
    ↓
Done
```

---

## Document & Text Processing Pipeline

### Overview
The document & text processing pipeline ingests long-form textual assets, source code repositories, and rich documents (PDF, EPUB, DOCX, PPTX, Markdown, HTML). It normalizes raw content, preserves semantic structure, generates dense embeddings for retrieval, and surfaces embedded media for downstream pipelines.

### Supported Formats
- Plain text (`.txt`, `.md`, `.rst`)
- Office documents (`.docx`, `.pptx`, `.xlsx` as structured tables)
- eBooks (`.pdf`, `.epub`, `.mobi`)
- Rich HTML and Markdown (including front matter metadata)
- Source code files (`.py`, `.js`, `.java`, `.ipynb` metadata only)

### Pipeline Stages

#### Stage 1: Discovery & Intake
**Module:** `src/documents/processor.py`

1. Expand `folder_uri` inputs recursively, respecting `.allocatorignore` patterns
2. Detect archives (`.zip`, `.tar`, `.rar`) and stream-extract contents without loading fully into memory
3. Register each discovered file as a virtual asset linked to the parent ingestion job
4. Identify container relationships (e.g., EPUB packages, DOCX zip bundles)

#### Stage 2: Parsing & Normalization
**Module:** `src/documents/processor.py`

1. Route each file to format-specific parser (`unstructured`, `pdfminer`, `python-docx`, `python-pptx`)
2. Preserve document structure (sections, headings, lists, tables, slide titles)
3. Normalize text encoding (UTF-8) and remove control characters
4. Extract metadata (author, title, TOC, publication date, slide numbers)

#### Stage 3: Chunking & Embedding
**Module:** `src/documents/chunker.py`, `src/documents/embedder.py`

1. Apply structure-aware chunking (heading-based, code-aware, slide-aware)
2. Generate semantic embeddings per chunk using `sentence-transformers` text models (768-d)
3. Maintain cross references to original page/slide offsets and anchors
4. Record cumulative token counts for paging and summarization budgets

#### Stage 4: Metadata Enrichment & Summaries
**Module:** `src/documents/processor.py`, `src/knowledge/organizer.py`

1. Produce extractive summaries (per document and per section)
2. Generate keywords, topics, and named entities
3. Align document topics with existing knowledge tree categories
4. Flag regulatory or PII-sensitive content for approval workflows

#### Stage 5: Embedded Media Extraction
**Module:** `src/documents/ocr.py`, `src/media/processor.py`

1. Detect embedded images (figures, diagrams, covers) and route them through the image heuristic pipeline
2. Extract audio/video attachments (e.g., embedded recordings) for media pipeline processing
3. Associate derived assets back to parent document chunks for cross-modal retrieval
4. Track relationships (`document_chunk_id`, `asset_id`) in `lineage` for provenance

#### Stage 6: Code & Notebook Handling
**Module:** `src/documents/chunker.py`

1. Detect code fences and tokenize using language-aware splitters
2. Generate additional embeddings focused on structural similarity (AST fingerprints)
3. For Jupyter notebooks, extract markdown + code cells, capture outputs as images, and route images to heuristics

### Flow Summary
```
Folder / Document Upload
    ↓
[Discovery & Intake]
    ↓
[Parsing & Normalization]
    ↓
[Chunking & Embedding]
    ↓
[Metadata Enrichment]
    ↓
[Embedded Media Extraction]
    ↓
[Knowledge Tree Alignment]
```

---

## JSON Processing Pipeline

### Overview
The JSON processing pipeline analyzes JSON documents, infers schemas, and decides between SQL and JSONB storage strategies.

### Pipeline Stages

#### Stage 1: JSON Parsing & Validation
**Module:** `src/ingest/validator.py`

**Input:** Raw JSON string from request

**Process:**
1. Parse JSON string to Python dict/list
2. Validate JSON structure:
   - Must be object `{}` or array `[]`
   - Reject primitives (strings, numbers) as top-level
3. If array: treat as batch, create one job per element
4. Extract basic metadata:
   - Size in bytes
   - Depth (nesting level)
   - Top-level key count

**Output:** Parsed JSON object(s)

**Error Handling:**
- Invalid JSON → return 400 error
- Empty object/array → return 400 error

---

#### Stage 2: Flattening & Structure Analysis
**Module:** `src/json/processor.py`

**Process:**
1. Flatten nested JSON to paths:
   - `{"user": {"name": "John"}}` → `{"user.name": "John"}`
   - Max depth: 3 (configurable)
2. For each path, record:
   - Data type (string, number, boolean, null, array, object)
   - Presence count (how many samples have this path)
   - Type stability (fraction of samples with same type)
   - Value examples (for schema generation)

**Example:**
```python
{
    "user.name": {
        "type": "string",
        "presence": 1.0,  # 100% of samples
        "type_stability": 1.0,  # Always string
        "examples": ["John", "Alice"]
    },
    "user.age": {
        "type": "number",
        "presence": 0.8,  # 80% of samples
        "type_stability": 1.0,
        "examples": [30, 25]
    }
}
```

**Output:** Flattened structure with statistics

---

#### Stage 3: Schema Decision Algorithm (SchemaDecider)
**Module:** `src/json/schema_decider.py`

**Purpose:** Deterministically decide between SQL and JSONB storage.

**Inputs:**
- Flattened structure statistics
- Sample size (N_sample = min(128, batch_size))
- Configurable thresholds

**Algorithm:**

**Step 1: Compute Stability Metrics**
```python
avg_field_stability = mean([path.type_stability for path in top_level_paths])
avg_presence = mean([path.presence for path in top_level_paths])
max_depth = max([path.depth for path in all_paths])
num_top_level_keys = len(top_level_paths)
has_array_of_objects = any(path.type == "array" and path.items_type == "object")
```

**Step 2: Apply Decision Rules**

**Prefer SQL if ALL of the following hold:**
1. `num_top_level_keys <= 20`
2. `avg_field_stability >= 0.6`
3. `max_depth <= 2`
4. `has_array_of_objects == False`
5. `avg_presence >= 0.5` (at least 50% of fields present in most samples)

**Otherwise prefer JSONB**

**Step 3: Detect Relationships**
- If field name ends with `_id` and has high cardinality:
  - Suggest foreign key relationship
  - Recommend separate table

**Step 4: Generate DDL Candidate (if SQL chosen)**
- Map JSON types to SQL types:
  - `string` → `text`
  - `number` → `numeric` or `integer` (if all integers)
  - `boolean` → `boolean`
  - `null` → nullable column
  - Arrays → `text[]` or separate table
- Add indexes on:
  - High-cardinality fields
  - Foreign key fields (`*_id`)
  - Frequently queried fields
- Always include `extra JSONB` column for flexibility

**Example DDL:**
```sql
CREATE TABLE user_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    age INTEGER,
    email TEXT UNIQUE,
    city TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    extra JSONB  -- For unexpected fields
);

CREATE INDEX idx_user_profiles_email ON user_profiles(email);
CREATE INDEX idx_user_profiles_city ON user_profiles(city);
```

**Output:**
- `storage_choice`: "sql" or "jsonb"
- `ddl`: SQL DDL string (if SQL chosen)
- `structure_hash`: SHA256 of normalized structure (for deduplication)
- `schema_proposal`: Complete proposal object

---

#### Stage 4: Schema Proposal Storage
**Module:** `src/catalog/models.py`

**Process:**
1. Check if schema with same `structure_hash` exists
2. If exists:
   - Link asset to existing schema
   - Increment `assets_count`
3. If new:
   - Create `schema_def` record:
     - `id` = UUID
     - `name` = auto-generated (e.g., "user_profiles_v1")
     - `storage_choice` = "sql" or "jsonb"
     - `ddl` = DDL string (if SQL)
     - `status` = "provisional"
     - `structure_hash` = hash
   - Notify admin UI (if configured)

**Output:** `schema_id` assigned to asset

---

#### Stage 5: Storage Materialization
**Module:** `src/json/processor.py`

**If SQL Chosen:**
1. Check if `schema.status == "active"`:
   - If active: proceed with insert
   - If provisional: store in temporary JSONB table, wait for approval
2. If active:
   - Ensure table exists (create if needed, idempotent)
   - Map JSON fields to SQL columns
   - Insert row into table
   - Store reference in `asset` record:
     - `storage_location` = table name
     - `storage_id` = row UUID

**If JSONB Chosen:**
1. Create collection table if not exists:
   ```sql
   CREATE TABLE IF NOT EXISTS docs_{collection_name} (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       doc JSONB NOT NULL,
       created_at TIMESTAMPTZ DEFAULT NOW()
   );
   CREATE INDEX idx_docs_{collection_name}_gin ON docs_{collection_name} USING GIN(doc);
   ```
2. Insert JSON document into collection table
3. Store reference in `asset` record:
   - `storage_location` = collection name
   - `storage_id` = document UUID

**Output:** Asset stored in appropriate storage backend

---

### JSON Processing Flow Diagram

```
JSON Payload
    ↓
[JSON Parsing & Validation]
    ├─→ Parse to dict/list
    └─→ Validate structure
    ↓
[Flattening & Structure Analysis]
    ├─→ Flatten nested paths (max depth 3)
    ├─→ Compute type statistics
    └─→ Compute presence/stability metrics
    ↓
[Schema Decision Algorithm]
    ├─→ Evaluate stability metrics
    ├─→ Apply decision rules
    ├─→ SQL vs JSONB decision
    └─→ Generate DDL (if SQL)
    ↓
[Schema Proposal Storage]
    ├─→ Check existing schema (by hash)
    ├─→ Create new schema_def (if new)
    └─→ Mark as provisional
    ↓
[Storage Materialization]
    ├─→ SQL Path:
    │   ├─→ Check schema status (active?)
    │   ├─→ Create table (if needed)
    │   └─→ Insert row
    └─→ JSONB Path:
        ├─→ Create collection table (if needed)
        └─→ Insert document
    ↓
Done
```

---

## Search & Retrieval Pipeline

### Overview
Semantic search using CLIP embeddings for text-to-image/video retrieval.

### Pipeline Stages

#### Stage 1: Query Processing
**Module:** `src/api/routes.py` → `src/catalog/queries.py`

**Input:** Query string, filters (type, owner, cluster, tags), optional target modality

**Process:**
1. Validate query (non-empty, length limits)
2. Parse filters and requested modality (`media`, `document`, `audio`, `json`, `mixed`)
3. Detect query intent (keyword vs semantic) and language
4. Encode query text using appropriate encoder:
   ```python
   media_query = clip_model.encode(query_text, normalize_embeddings=True)
   doc_query = text_model.encode(query_text, normalize_embeddings=True)
   ```
5. Generate optional keyword search terms for hybrid ranking

**Output:** Multi-vector query bundle (`media_query`, `doc_query`, transcript token set)

---

#### Stage 2: Vector Similarity Search
**Module:** `src/catalog/queries.py`

**Process:**
1. Build SQL queries across modalities:
   ```sql
   -- Media ANN
   SELECT a.id, a.uri, a.tags, a.cluster_id,
          1 - (a.embedding <=> %s::vector) AS similarity,
          'media'::text AS modality
   FROM asset a
   WHERE a.kind = 'media'
     AND a.status = 'done'
     AND a.embedding IS NOT NULL
     AND (a.owner = %s OR %s IS NULL)
     AND (a.cluster_id = %s::uuid OR %s IS NULL)
     AND (a.tags && %s::text[] OR %s IS NULL)
   UNION ALL
   -- Document chunks
   SELECT dc.id, dc.uri, dc.tags, dc.parent_asset_id AS cluster_id,
          1 - (dc.text_embedding <=> %s::vector) AS similarity,
          'document'::text AS modality
   FROM document_chunk dc
   WHERE (dc.owner = %s OR %s IS NULL)
     AND (dc.asset_id = %s::uuid OR %s IS NULL)
   UNION ALL
   -- Audio transcripts
   SELECT at.id, at.uri, at.tags, at.asset_id AS cluster_id,
          1 - (at.text_embedding <=> %s::vector) AS similarity,
          'audio'::text AS modality
   FROM audio_transcript at
   WHERE at.embedding IS NOT NULL
   ORDER BY similarity DESC
   LIMIT %s;
   ```
2. Execute queries with modality-specific vectors and combine results
3. Filter results by `similarity >= threshold` and optionally blend BM25 keyword scores

**Technology:**
- `pgvector` `<=>` operator for cosine distance
- HNSW index (if available) for fast ANN search

**Performance:**
- Target: < 100ms for top-10 results
- Index: `CREATE INDEX ON asset USING hnsw (embedding vector_cosine_ops);`

---

#### Stage 3: Result Formatting
**Module:** `src/api/routes.py`

**Process:**
1. Enrich results with:
   - Cluster metadata
   - Thumbnail URIs or document snippet previews
   - Transcript excerpts and highlighting spans
   - Knowledge tree path (e.g., `Books > Ursula K. Le Guin > Sci-Fi`)
2. Interleave modalities based on re-ranking policy (critical → promote document/media mix)
3. Sort by blended similarity score and knowledge tree relevance
4. Limit to requested `limit`
5. Format response JSON with modality annotations and hierarchical breadcrumbs

**Output:** Search results array

---

### Search Flow Diagram

```
Query Text + Filters
    ↓
[Query Processing]
    ├─→ CLIP text encoder → media_query
    ├─→ Text encoder → doc_query
    └─→ Keyword expansion / language detection
    ↓
[Vector Similarity Search]
    ├─→ Media ANN (asset.embedding)
    ├─→ Document ANN (document_chunk.text_embedding)
    └─→ Audio transcript ANN (audio_transcript.text_embedding)
    ↓
[Knowledge Tree Re-Ranker]
    ├─→ Merge modalities
    ├─→ Apply guardrails & hierarchical boosts
    └─→ Enforce similarity thresholds
    ↓
[Result Formatting]
    ├─→ Enrich with metadata + snippets
    ├─→ Attach knowledge tree breadcrumbs
    └─→ Limit results
    ↓
JSON Response
```

---

## Semantic Knowledge Organization

### Overview
The semantic knowledge organization pipeline builds and maintains a prioritized hierarchy (e.g., `Books → Authors → Genres`) that groups semantically similar assets. It enables guided exploration, context-aware search boosts, and guardrail-enforced content placement powered by LLM reasoning.

### Objectives (Critical)
- Automatically organize processed assets into a tree-aligned taxonomy after ingestion
- Preserve explainability for every placement decision via LLM-generated rationales
- Enforce guardrails to prevent drift, duplication, or cyclic relationships
- Expose hierarchy paths for UI navigation and relevance boosting during search

### Pipeline Stages

#### Stage 1: Similarity Graph Construction
**Module:** `src/knowledge/organizer.py`

1. Build modality-specific kNN graphs from embeddings (media, documents, audio)
2. Merge graphs into a unified similarity matrix with modality weighting
3. Detect candidate clusters using community detection (Louvain / Leiden)

#### Stage 2: LLM-Based Node Labeling
**Module:** `src/knowledge/organizer.py`

1. Summarize each candidate cluster using representative assets
2. Call the LLM with structured prompts to propose node names and hierarchy levels
3. Produce fallback names using deterministic heuristics when LLM confidence is low

#### Stage 3: Guardrails & Validation
**Module:** `src/knowledge/guardrails.py`

1. Validate proposed nodes against policy rules (PII, sensitive terms, profanity)
2. Enforce unique path constraints and prevent cycles
3. Apply similarity thresholds required for critical placement decisions
4. Persist approved nodes in `knowledge_node` table with versioning

#### Stage 4: Tree Assembly & Prioritization
**Module:** `src/knowledge/tree_models.py`

1. Assemble parent-child relationships based on LLM recommendations and guardrail output
2. Compute priority scores (recency, user access frequency, semantic coherence)
3. Update cluster centroids with aggregated embeddings for each node
4. Publish diff events for downstream consumers (UI, search re-ranker)

#### Stage 5: Continuous Learning
**Module:** `src/knowledge/organizer.py`

1. Monitor new assets for taxonomy drift; trigger partial re-balancing when needed
2. Allow admins to approve or override node placements (human-in-the-loop)
3. Version the tree and maintain changelog entries in `lineage`

### Outputs
- `knowledge_node` records with hierarchy metadata and guardrail status
- `knowledge_edge` relationships capturing parent-child links
- Placement rationale stored alongside lineage for auditability
- Boosting hints fed back into the search re-ranker

---

## Admin Operations Pipeline

### Overview
Admin operations for reviewing and approving provisional decisions.

### Operations

#### 1. Schema Approval
**Endpoint:** `POST /api/v1/schemas/{schema_id}/approve`

**Process:**
1. Load schema proposal (`schema_def` record)
2. Validate schema status is "provisional"
3. If SQL schema:
   - Execute DDL migration (idempotent)
   - Create table/indexes
   - Update `schema_def.status` = "active"
   - Migrate any temporary JSONB records to SQL table
4. If JSONB schema:
   - Update `schema_def.status` = "active"
5. Update all linked assets to use new schema
6. Log action in `lineage` table

**Rollback:**
- Keep original JSONB records
- Mark schema as "rejected" instead of deleting

---

#### 2. Cluster Management
**Endpoint:** `PATCH /api/v1/clusters/{cluster_id}`

**Operations:**

**Rename:**
- Update `cluster.name`
- Update `cluster.updated_at`

**Merge:**
- Select target cluster (keep)
- Select source clusters (merge into target)
- Update all assets: `cluster_id` → target cluster
- Recompute target centroid: mean of all embeddings
- Delete source clusters
- Log merge action

**Update Threshold:**
- Update `cluster.threshold`
- Optionally re-evaluate cluster assignments

**Confirm/Reject:**
- Update `cluster.provisional` flag
- If rejected: mark assets for re-clustering

---

#### 3. Schema Rejection
**Endpoint:** `POST /api/v1/schemas/{schema_id}/reject`

**Process:**
1. Update `schema_def.status` = "rejected"
2. Re-process affected assets:
   - Re-run SchemaDecider
   - Create new schema proposal
   - Store in JSONB fallback

---

## Data Models & Database Schema

### Core Tables

#### `asset_raw`
Immutable record of every raw upload.

```sql
CREATE TABLE asset_raw (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id TEXT NOT NULL,
    part_id TEXT NOT NULL,
    uri TEXT NOT NULL,  -- Storage path
    size_bytes BIGINT NOT NULL,
    content_type TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(request_id, part_id)
);

CREATE INDEX idx_asset_raw_request_id ON asset_raw(request_id);
```

#### `asset`
Canonical metadata for all assets.

```sql
CREATE TABLE asset (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind TEXT CHECK (kind IN ('media', 'json', 'document', 'audio')) NOT NULL,
    uri TEXT,  -- NULL for JSON stored in SQL tables
    sha256 TEXT,
    content_type TEXT,
    size_bytes BIGINT,
    owner TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT DEFAULT 'processing',
    cluster_id UUID REFERENCES cluster(id),
    schema_id UUID REFERENCES schema_def(id),
    tags TEXT[],
    embedding vector(512),  -- pgvector type
    text_embedding vector(768),  -- Document/audio transcript embeddings
    storage_location TEXT,  -- Table/collection name
    storage_id UUID,  -- Row/document ID
    metadata JSONB  -- Additional metadata (EXIF, etc.)
);

CREATE INDEX idx_asset_cluster_id ON asset(cluster_id);
CREATE INDEX idx_asset_schema_id ON asset(schema_id);
CREATE INDEX idx_asset_status ON asset(status);
CREATE INDEX idx_asset_tags_gin ON asset USING GIN(tags);
CREATE INDEX idx_asset_embedding_hnsw ON asset USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_asset_text_embedding_hnsw ON asset USING hnsw (text_embedding vector_cosine_ops);
```

#### `cluster`
Media clusters with centroid vectors.

```sql
CREATE TABLE cluster (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    centroid vector(512) NOT NULL,
    threshold REAL DEFAULT 0.72,
    provisional BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cluster_centroid_hnsw ON cluster USING hnsw (centroid vector_cosine_ops);
```

#### `schema_def`
Schema proposals and definitions.

```sql
CREATE TABLE schema_def (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    structure_hash TEXT UNIQUE NOT NULL,
    storage_choice TEXT CHECK (storage_choice IN ('sql', 'jsonb')) NOT NULL,
    version INTEGER DEFAULT 1,
    ddl TEXT,  -- SQL DDL if storage_choice = 'sql'
    status TEXT DEFAULT 'provisional' CHECK (status IN ('provisional', 'active', 'rejected')),
    assets_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_schema_def_status ON schema_def(status);
CREATE INDEX idx_schema_def_storage_choice ON schema_def(storage_choice);
```

#### `lineage`
Audit trail for all processing stages.

```sql
CREATE TABLE lineage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id TEXT NOT NULL,
    asset_id UUID REFERENCES asset(id),
    schema_id UUID REFERENCES schema_def(id),
    stage TEXT NOT NULL,  -- 'ingest', 'processing', 'done', 'failed'
    detail JSONB,  -- Stage-specific details
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_lineage_request_id ON lineage(request_id);
CREATE INDEX idx_lineage_asset_id ON lineage(asset_id);
CREATE INDEX idx_lineage_stage ON lineage(stage);
```

#### `video_frame`
Per-frame embeddings for videos.

```sql
CREATE TABLE video_frame (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES asset(id) NOT NULL,
    frame_idx INTEGER NOT NULL,
    timestamp REAL,  -- Seconds into video
    embedding vector(512) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(asset_id, frame_idx)
);

CREATE INDEX idx_video_frame_asset_id ON video_frame(asset_id);
CREATE INDEX idx_video_frame_embedding_hnsw ON video_frame USING hnsw (embedding vector_cosine_ops);
```

---

#### `document_chunk`
Flattened document sections with embeddings.

```sql
CREATE TABLE document_chunk (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES asset(id) NOT NULL,
    uri TEXT,
    title TEXT,
    heading_path TEXT[],  -- e.g., {Chapter 1, Section A}
    text TEXT NOT NULL,
    text_embedding vector(768) NOT NULL,
    chunk_index INTEGER NOT NULL,
    tokens_count INTEGER,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(asset_id, chunk_index)
);

CREATE INDEX idx_document_chunk_asset_id ON document_chunk(asset_id);
CREATE INDEX idx_document_chunk_text_embedding_hnsw ON document_chunk USING hnsw (text_embedding vector_cosine_ops);
CREATE INDEX idx_document_chunk_heading_path_gin ON document_chunk USING GIN(heading_path);
```

#### `audio_segment`
Segment-level metadata for audio assets.

```sql
CREATE TABLE audio_segment (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES asset(id) NOT NULL,
    segment_index INTEGER NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    kind TEXT CHECK (kind IN ('speech', 'music', 'noise')) NOT NULL,
    embedding vector(512),
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(asset_id, segment_index)
);

CREATE INDEX idx_audio_segment_asset_id ON audio_segment(asset_id);
CREATE INDEX idx_audio_segment_embedding_hnsw ON audio_segment USING hnsw (embedding vector_cosine_ops);
```

#### `audio_transcript`
Textual transcripts aligned to audio segments.

```sql
CREATE TABLE audio_transcript (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES asset(id) NOT NULL,
    segment_id UUID REFERENCES audio_segment(id),
    text TEXT NOT NULL,
    text_embedding vector(768) NOT NULL,
    language TEXT,
    speaker_label TEXT,
    confidence REAL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audio_transcript_asset_id ON audio_transcript(asset_id);
CREATE INDEX idx_audio_transcript_text_embedding_hnsw ON audio_transcript USING hnsw (text_embedding vector_cosine_ops);
```

#### `knowledge_node`
Hierarchy nodes for semantic organization.

```sql
CREATE TABLE knowledge_node (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    path TEXT[] NOT NULL,
    depth INTEGER NOT NULL,
    summary TEXT,
    guardrail_status TEXT CHECK (guardrail_status IN ('pending', 'approved', 'rejected')) DEFAULT 'pending',
    embedding vector(768),
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(path)
);

CREATE INDEX idx_knowledge_node_depth ON knowledge_node(depth);
CREATE INDEX idx_knowledge_node_path_gin ON knowledge_node USING GIN(path);
CREATE INDEX idx_knowledge_node_embedding_hnsw ON knowledge_node USING hnsw (embedding vector_cosine_ops);
```

#### `knowledge_edge`
Parent-child relationships for the knowledge tree.

```sql
CREATE TABLE knowledge_edge (
    parent_id UUID REFERENCES knowledge_node(id) ON DELETE CASCADE,
    child_id UUID REFERENCES knowledge_node(id) ON DELETE CASCADE,
    priority_score REAL,
    rationale TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (parent_id, child_id)
);

CREATE INDEX idx_knowledge_edge_parent ON knowledge_edge(parent_id);
CREATE INDEX idx_knowledge_edge_child ON knowledge_edge(child_id);
```

---

## Storage Architecture

### Storage Backend Abstraction

**Interface:** `src/storage/adapter.py`

```python
class StorageAdapter:
    def store_raw(self, request_id: str, part_id: str, data: bytes) -> str:
        """Store raw bytes, return URI"""
        
    def move_to_cluster(self, source_uri: str, cluster_id: str, asset_id: str) -> str:
        """Move file to cluster directory, return new URI"""
        
    def store_derived(self, cluster_id: str, asset_id: str, filename: str, data: bytes) -> str:
        """Store derived asset (thumbnail, etc.), return URI"""
        
    def get(self, uri: str) -> bytes:
        """Retrieve file by URI"""
        
    def delete(self, uri: str) -> None:
        """Delete file by URI"""
```

### Filesystem Backend (`fs://`)

**Structure:**
```
storage/
├── incoming/
│   └── {request_id}/
│       └── {part_id}.{ext}
│       └── chunks/{chunk_id}.json  # normalized document chunks
├── media/
│   ├── clusters/
│   │   └── {cluster_id}/
│   │       └── {asset_id}.{ext}
│   └── derived/
│       └── {cluster_id}/
│           └── {asset_id}/
│               ├── thumb.jpg
│               └── ...
├── documents/
│   └── {asset_id}/
│       ├── chunks/{chunk_index}.json
│       └── embedded_media/{derived_asset_id}.{ext}
└── audio/
    └── {asset_id}/
        ├── segments/{segment_index}.wav
        └── transcripts/{segment_index}.json
└── json/
    └── (temporary JSONB storage, if needed)
```

### S3 Backend (`s3://`)

**Structure:**
```
s3://bucket-name/
├── incoming/{request_id}/{part_id}.{ext}
├── incoming/{request_id}/chunks/{chunk_id}.json
├── media/clusters/{cluster_id}/{asset_id}.{ext}
├── media/derived/{cluster_id}/{asset_id}/thumb.jpg
├── documents/{asset_id}/chunks/{chunk_index}.json
├── documents/{asset_id}/embedded_media/{derived_asset_id}.{ext}
├── audio/{asset_id}/segments/{segment_index}.wav
├── audio/{asset_id}/transcripts/{segment_index}.json
└── json/{collection_name}/{document_id}.json
```

**Configuration:**
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION`
- `S3_BUCKET`

---

## Error Handling & Resilience

### Error Categories

1. **Validation Errors (400)**
   - Invalid JSON format
   - Missing required fields
   - File size/type limits exceeded
   - **Response:** Clear error message with details

2. **Not Found Errors (404)**
   - Job/asset/cluster/schema not found
   - **Response:** `{"error": "Resource not found", "resource_type": "...", "id": "..."}`

3. **Conflict Errors (409)**
   - Duplicate idempotency key
   - Schema merge conflicts
   - **Response:** `{"error": "Conflict", "details": "..."}`

4. **Processing Errors (500)**
   - Database connection failures
   - Storage backend failures
   - Embedding model failures
   - **Response:** `{"error": "Internal server error", "request_id": "...", "details": "..."}`

### Retry Strategy

**For Transient Failures:**
- Database connection: 3 retries with exponential backoff
- Storage operations: 3 retries with exponential backoff
- Embedding generation: 2 retries (model may be busy)

**For Permanent Failures:**
- Mark job as `failed` in database
- Log error details in `lineage` table
- Send notification (if configured)

### Idempotency

- All operations are idempotent via `idempotency_key`
- Duplicate requests return existing job_id
- File deduplication via SHA256 hash

---

## Performance Targets

### API Latency (p95)
- `POST /ingest`: < 200ms (acknowledgment)
- `GET /ingest/{job_id}/status`: < 50ms
- `GET /objects/{system_id}`: < 100ms
- `GET /search`: < 150ms (with ANN index)
- `PATCH /clusters/{cluster_id}`: < 200ms

### Processing Latency (p95)
- Image processing: < 1.5s per image
- Video processing: < 5s per video (3 keyframes)
- JSON processing: < 500ms per document
- Schema decision: < 200ms per batch

### Throughput
- Ingestion: 100 requests/second (acknowledgment)
- Processing: 10-20 assets/second (depending on media type)
- Search: 50 queries/second

### Resource Usage (per worker)
- CPU: 2-4 cores (for CLIP inference)
- Memory: 2-4 GB (model + batch processing)
- Disk: Depends on storage backend

---

## Configuration Reference

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/file_allocator
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# Storage
STORAGE_BACKEND=fs://  # or s3://
STORAGE_PATH=./storage

# S3 (if using s3://)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
S3_BUCKET=file-allocator

# Application
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=false
LOG_LEVEL=INFO

# Workers
WORKER_THREADS=4
QUEUE_BACKEND=inproc  # or redis
REDIS_URL=redis://localhost:6379/0

# Media Processing
EMBEDDING_MODEL=clip-ViT-B-32
EMBEDDING_DIM=512
CLUSTER_THRESHOLD=0.72
MAX_IMAGE_SIZE=1024
VIDEO_KEYFRAMES=3
OCR_ENABLED=true
OCR_TEXT_HEURISTIC_THRESHOLD=0.65

# Document Processing
TEXT_EMBEDDING_MODEL=gte-base
DOC_CHUNK_SIZE=900
DOC_CHUNK_OVERLAP=150
FOLDER_INGESTION_ENABLED=false  # Future enhancement flag

# Audio Processing
TRANSCRIPTION_MODEL=faster-whisper-large-v3
AUDIO_SEGMENT_SECONDS=30
AUDIO_SPEECH_CONFIDENCE=0.55
AUDIO_SPECTROGRAM_IMAGE_SIZE=512

# VLM Configuration
GEMINI_API_KEY=  # Required for VLM analysis
GEMINI_MODEL=gemini-2.5-flash  # or gemini-2.5-flash-lite
VLM_ENABLED=true
VLM_TIMEOUT=5  # seconds
VLM_FALLBACK_TO_CLIP=true  # Use CLIP if VLM fails

# Schema Decision
SCHEMA_SAMPLE_SIZE=128
SCHEMA_STABILITY_THRESHOLD=0.6
SCHEMA_MAX_TOP_LEVEL_KEYS=20
SCHEMA_MAX_DEPTH=2
AUTO_MIGRATE=false

# Knowledge Organization
KNOWLEDGE_TREE_ENABLED=true
KNOWLEDGE_TREE_REFRESH_INTERVAL_MINUTES=10
KNOWLEDGE_GUARDRAIL_THRESHOLD=0.72
LLM_PROVIDER=gemini  # or openai, anthropic
LLM_MODEL_NAME=gemini-2.5-flash

# Security
API_KEY=  # Optional
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000

# Observability
METRICS_ENABLED=true
TRACING_ENABLED=false
```

---

## Implementation Checklist

### Phase 1: Core Infrastructure
- [ ] Database schema migration (Alembic)
- [ ] Storage adapter (filesystem backend)
- [ ] Basic FastAPI routes (stubs)
- [ ] Configuration management
- [ ] Health checks

### Phase 2: Ingestion Pipeline
- [ ] Request validation
- [ ] Raw storage persistence
- [ ] Job queue (in-process)
- [ ] Lineage tracking
- [ ] Status endpoint
- [ ] Recursive folder ingestion (`folder_uri`) expansion _(Future Enhancement)_

### Phase 3: Media Processing
- [ ] Media classification
- [ ] Image normalization
- [ ] Video keyframe extraction
- [ ] CLIP embedding generation
- [ ] Tag generation
- [ ] Deduplication
- [ ] Clustering
- [ ] Text-in-image heuristic with OCR routing _(Critical Enhancement)_
- [ ] OCR metadata propagation to document chunks _(Critical Enhancement)_

### Phase 4: Document & Text Processing _(Critical)_
- [ ] Multi-format parsing via `unstructured`
- [ ] Structure-aware chunking (headings, slides, code blocks)
- [ ] Text embedding generation (768-d)
- [ ] Embedded media extraction and routing
- [ ] Section-level summarization & keyword extraction
- [ ] Source map + lineage linking for chunks

### Phase 5: Audio Intelligence _(Future Enhancement)_
- [ ] VAD + speech vs non-speech heuristic
- [ ] Faster-Whisper transcription pipeline
- [ ] Transcript embedding generation
- [ ] Spectrogram embeddings for music/ambient audio
- [ ] Genre / mood classification metadata

### Phase 6: JSON Processing
- [ ] JSON parsing & validation
- [ ] Structure flattening
- [ ] SchemaDecider algorithm
- [ ] DDL generation
- [ ] Schema proposal storage
- [ ] SQL/JSONB materialization

### Phase 7: Multi-Modal Search & Retrieval _(Critical)_
- [ ] Multi-vector query encoding (media + documents + audio)
- [ ] Unified ANN search across `asset`, `document_chunk`, `audio_transcript`
- [ ] Hybrid re-ranking (semantic + keyword)
- [ ] Knowledge tree breadcrumb enrichment
- [ ] Filter extensions (modality, author, hierarchy path)

### Phase 8: Semantic Knowledge Organization _(Critical)_
- [ ] Similarity graph construction across modalities
- [ ] LLM-driven node naming & summarization
- [ ] Guardrail enforcement and approval workflow
- [ ] Knowledge tree persistence (`knowledge_node`, `knowledge_edge`)
- [ ] Change notifications for downstream systems

### Phase 9: Admin Operations
- [ ] Schema approval/rejection
- [ ] Cluster management
- [ ] Admin UI backend endpoints
- [ ] Knowledge tree review tools _(Critical)_

### Phase 10: Production Readiness
- [ ] Error handling & retries
- [ ] Logging & monitoring
- [ ] S3 storage backend
- [ ] Redis queue backend
- [ ] Performance optimization
- [ ] Documentation

---

## Conclusion

This specification provides a complete technical blueprint for implementing the Automated File Allocator system using Python and FastAPI. The architecture prioritizes:

1. **Simplicity**: Monolithic design with clear module boundaries
2. **Performance**: CPU-friendly ML models, efficient vector search
3. **Flexibility**: Storage abstraction, configurable thresholds
4. **Reliability**: Idempotent operations, audit trails, error handling
5. **Extensibility**: Clear interfaces for future enhancements

The system is designed to handle both media files and JSON documents through a unified API, with intelligent processing pipelines that automatically organize and store data optimally.

---

**Document Version:** 1.0  
**Last Updated:** 2025 
**Status:** Ready for Implementation

-