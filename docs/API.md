# API Documentation

RESTful API for the Automated File Allocator system.

Base URL: `http://localhost:8000`

## Authentication

Currently no authentication required (add your auth implementation here).

## Endpoints

### Health & Status Endpoints

**GET** `/` - Root endpoint with service info

**GET** `/health` - Health check

**GET** `/live` - Liveness probe

**GET** `/ready` - Readiness probe with database check

**Response Examples:**

```json
// /health or /live
{
  "status": "healthy"
}

// /ready
{
  "status": "ready",
  "database": "connected"
}
```

---

### Ingest Files

**POST** `/api/v1/ingest`

Upload media files or JSON documents for processing.

**Request:**

- Content-Type: `multipart/form-data`
- Body:
  - `files[]` (file, optional): Media files to upload
  - `payload` (JSON string, optional): JSON document to ingest
  - `owner` (string, optional): Owner identifier
  - `comments` (string, optional): Additional comments

**Example:**

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -F "files[]=@image.jpg" \
  -F "owner=user123"
```

**Response:**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "system_ids": ["7dd0d6ce-b8a1-44ca-bcc5-b607eeb5248a"],
  "status": "accepted",
  "message": "Job accepted for processing"
}
```

---

### Get Job Status

**GET** `/api/v1/ingest/{job_id}/status`

Check the status of an ingestion job.

**Response:**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "done",
  "created_at": "2025-11-14T10:30:00Z",
  "completed_at": "2025-11-14T10:30:15Z",
  "asset_ids": ["7dd0d6ce-b8a1-44ca-bcc5-b607eeb5248a"],
  "error_message": null
}
```

**Status Values:**

- `queued` - Job is waiting to be processed
- `processing` - Job is currently being processed
- `done` - Job completed successfully
- `failed` - Job failed (check error_message)

---

### Search Media

**POST** `/api/v1/search`

Semantic search for media using text queries.

**Request:**

```json
{
  "query": "sunset at the beach",
  "limit": 10,
  "threshold": 0.75,
  "filters": {
    "kind": "media",
    "owner": "user123"
  }
}
```

**Response:**

```json
{
  "results": [
    {
      "asset_id": "7dd0d6ce-b8a1-44ca-bcc5-b607eeb5248a",
      "uri": "fs://media/cluster-uuid/asset-uuid/image.jpg",
      "similarity": 0.92,
      "kind": "media",
      "content_type": "image/jpeg",
      "owner": "user123"
    }
  ],
  "count": 1,
  "query_time_ms": 45.2
}
```

---

### List Clusters

**GET** `/api/v1/clusters`

Get all media clusters.

**Query Parameters:**

- `status` (optional): Filter by status (`provisional` or `active`)

**Response:**

```json
{
  "clusters": [
    {
      "id": "cluster-uuid",
      "name": "Sunset Photos",
      "centroid": [0.1, 0.2, ...],
      "asset_count": 15,
      "status": "active",
      "created_at": "2025-11-14T10:00:00Z"
    }
  ],
  "count": 1
}
```

---

### Get Cluster Details

**GET** `/api/v1/clusters/{cluster_id}`

Get detailed information about a specific cluster.

**Response:**

```json
{
  "id": "cluster-uuid",
  "name": "Sunset Photos",
  "status": "active",
  "asset_count": 15,
  "assets": [
    {
      "id": "asset-uuid",
      "uri": "fs://media/cluster-uuid/asset-uuid/image.jpg",
      "content_type": "image/jpeg",
      "created_at": "2025-11-14T10:30:00Z"
    }
  ]
}
```

---

### Approve Cluster

**POST** `/api/v1/clusters/{cluster_id}/approve`

Approve a provisional cluster (admin operation).

**Request:**

```json
{
  "name": "Beach Sunsets"
}
```

**Response:**

```json
{
  "id": "cluster-uuid",
  "status": "active",
  "message": "Cluster approved"
}
```

---

### List Schemas

**GET** `/api/v1/schemas`

Get all JSON schemas.

**Query Parameters:**

- `status` (optional): Filter by status (`provisional` or `active`)

**Response:**

```json
{
  "schemas": [
    {
      "id": "schema-uuid",
      "structure_hash": "abc123...",
      "storage_choice": "sql",
      "status": "provisional",
      "sample_size": 100,
      "created_at": "2025-11-14T10:00:00Z"
    }
  ],
  "count": 1
}
```

---

### Approve Schema

**POST** `/api/v1/schemas/{schema_id}/approve`

Approve a provisional schema and create SQL tables (admin operation).

**Response:**

```json
{
  "id": "schema-uuid",
  "status": "active",
  "table_name": "json_schema_abc123",
  "message": "Schema approved and table created"
}
```

---

## Error Responses

All endpoints may return error responses in this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**Common HTTP Status Codes:**

- `200 OK` - Request successful
- `400 Bad Request` - Invalid request parameters
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error (check logs)
