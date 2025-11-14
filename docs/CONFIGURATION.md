# Configuration Reference

Complete reference for all environment variables and configuration options.

## Database Configuration

| Variable          | Type   | Default                                                        | Description                                    |
| ----------------- | ------ | -------------------------------------------------------------- | ---------------------------------------------- |
| `DATABASE_URL`    | string | `postgresql://postgres:postgres@localhost:5432/file_allocator` | PostgreSQL connection string                   |
| `DB_POOL_SIZE`    | int    | `10`                                                           | Maximum number of database connections in pool |
| `DB_MAX_OVERFLOW` | int    | `20`                                                           | Maximum overflow connections beyond pool size  |

**Example:**

```env
DATABASE_URL=postgresql://user:pass@host:5432/dbname
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40
```

## Storage Configuration

| Variable          | Type   | Default     | Description                 |
| ----------------- | ------ | ----------- | --------------------------- |
| `STORAGE_BACKEND` | string | `fs://`     | Storage backend: `fs://`    |
| `STORAGE_PATH`    | string | `./storage` | Path for filesystem storage |

**Example:**

```env
STORAGE_BACKEND=fs://
STORAGE_PATH=/mnt/storage
```

## Application Configuration

| Variable    | Type   | Default   | Description                                                |
| ----------- | ------ | --------- | ---------------------------------------------------------- |
| `APP_HOST`  | string | `0.0.0.0` | Host to bind application server                            |
| `APP_PORT`  | int    | `8000`    | Port to bind application server                            |
| `DEBUG`     | bool   | `false`   | Enable debug mode (verbose logging, auto-reload)           |
| `LOG_LEVEL` | string | `INFO`    | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

**Example:**

```env
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=false
LOG_LEVEL=INFO
```

## Worker Configuration

| Variable         | Type   | Default                    | Description                                       |
| ---------------- | ------ | -------------------------- | ------------------------------------------------- |
| `WORKER_THREADS` | int    | `4`                        | Number of worker threads for job processing       |
| `QUEUE_BACKEND`  | string | `inproc`                   | Queue backend: `inproc` or `redis`                |
| `REDIS_URL`      | string | `redis://localhost:6379/0` | Redis connection URL (when using `redis` backend) |

**Example - In-Process Queue:**

```env
WORKER_THREADS=8
QUEUE_BACKEND=inproc
```

**Example - Redis Queue:**

```env
WORKER_THREADS=4
QUEUE_BACKEND=redis
REDIS_URL=redis://redis:6379/0
```

## Media Processing Configuration

| Variable            | Type   | Default                        | Description                                |
| ------------------- | ------ | ------------------------------ | ------------------------------------------ |
| `EMBEDDING_MODEL`   | string | `openai/clip-vit-base-patch32` | CLIP model for embeddings                  |
| `EMBEDDING_DIM`     | int    | `512`                          | Embedding dimension size                   |
| `CLUSTER_THRESHOLD` | float  | `0.72`                         | Similarity threshold for clustering        |
| `MAX_IMAGE_SIZE`    | int    | `1024`                         | Maximum image dimension (pixels)           |
| `VIDEO_KEYFRAMES`   | int    | `3`                            | Number of keyframes to extract from videos |

**Example:**

```env
EMBEDDING_MODEL=openai/clip-vit-base-patch32
CLUSTER_THRESHOLD=0.75
MAX_IMAGE_SIZE=1024
VIDEO_KEYFRAMES=5
```

## VLM Configuration

| Variable               | Type   | Default            | Description                   |
| ---------------------- | ------ | ------------------ | ----------------------------- |
| `GEMINI_API_KEY`       | string | `""`               | Google Gemini API key         |
| `GEMINI_MODEL`         | string | `gemini-2.5-flash` | Gemini model to use           |
| `VLM_ENABLED`          | bool   | `true`             | Enable VLM analysis           |
| `VLM_TIMEOUT`          | int    | `5`                | VLM API timeout (seconds)     |
| `VLM_FALLBACK_TO_CLIP` | bool   | `true`             | Fallback to CLIP if VLM fails |

**Example:**

```env
GEMINI_API_KEY=AIzaSyABCDEF1234567890
GEMINI_MODEL=gemini-2.5-flash
VLM_ENABLED=true
VLM_TIMEOUT=5
VLM_FALLBACK_TO_CLIP=true
```

## Schema Decision Configuration

| Variable                     | Type  | Default | Description                       |
| ---------------------------- | ----- | ------- | --------------------------------- |
| `SCHEMA_SAMPLE_SIZE`         | int   | `128`   | Sample size for schema analysis   |
| `SCHEMA_STABILITY_THRESHOLD` | float | `0.6`   | Threshold for schema stability    |
| `SCHEMA_MAX_TOP_LEVEL_KEYS`  | int   | `20`    | Max keys before triggering JSONB  |
| `SCHEMA_MAX_DEPTH`           | int   | `2`     | Max nesting depth for SQL columns |
| `AUTO_MIGRATE`               | bool  | `false` | Automatically run migrations      |

**Example:**

```env
SCHEMA_SAMPLE_SIZE=256
SCHEMA_STABILITY_THRESHOLD=0.7
SCHEMA_MAX_TOP_LEVEL_KEYS=15
AUTO_MIGRATE=false
```

## Search Configuration

| Variable                   | Type  | Default | Description                      |
| -------------------------- | ----- | ------- | -------------------------------- |
| `SEARCH_DEFAULT_LIMIT`     | int   | `10`    | Default number of search results |
| `SEARCH_MAX_LIMIT`         | int   | `100`   | Maximum number of search results |
| `SEARCH_DEFAULT_THRESHOLD` | float | `0.5`   | Default similarity threshold     |
| `SEARCH_TIMEOUT_SECONDS`   | int   | `30`    | Search query timeout             |

**Example:**

```env
SEARCH_DEFAULT_LIMIT=20
SEARCH_MAX_LIMIT=200
SEARCH_DEFAULT_THRESHOLD=0.6
```

## Security Configuration

| Variable          | Type   | Default                                              | Description                                                    |
| ----------------- | ------ | ---------------------------------------------------- | -------------------------------------------------------------- |
| `API_KEY`         | string | `""`                                                 | API key for authentication (if set, required for all requests) |
| `ALLOWED_ORIGINS` | list   | `["http://localhost:3000", "http://localhost:8000"]` | CORS allowed origins (comma-separated)                         |

**Example:**

```env
API_KEY=your_secure_api_key_here
ALLOWED_ORIGINS=https://app.example.com,https://admin.example.com
```

## Observability Configuration

| Variable          | Type | Default | Description                  |
| ----------------- | ---- | ------- | ---------------------------- |
| `METRICS_ENABLED` | bool | `true`  | Enable Prometheus metrics    |
| `TRACING_ENABLED` | bool | `false` | Enable OpenTelemetry tracing |

**Example:**

```env
METRICS_ENABLED=true
TRACING_ENABLED=false
```

## Complete Example Configuration

### Development

```env
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/file_allocator
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10

# Storage
STORAGE_BACKEND=fs://
STORAGE_PATH=./storage

# Application
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=true
LOG_LEVEL=DEBUG

# Workers
WORKER_THREADS=2
QUEUE_BACKEND=inproc

# Media
EMBEDDING_MODEL=openai/clip-vit-base-patch32
CLUSTER_THRESHOLD=0.72

# VLM
GEMINI_API_KEY=your_dev_api_key
VLM_ENABLED=true
VLM_FALLBACK_TO_CLIP=true

# Observability
METRICS_ENABLED=true
TRACING_ENABLED=false
```

### Production

```env
# Database
DATABASE_URL=postgresql://prod_user:secure_pass@db.example.com:5432/file_allocator
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40

# Storage
STORAGE_BACKEND=fs://
STORAGE_PATH=/app/storage

# Application
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=false
LOG_LEVEL=INFO

# Workers
WORKER_THREADS=8
QUEUE_BACKEND=redis
REDIS_URL=redis://redis.example.com:6379/0

# Media
EMBEDDING_MODEL=openai/clip-vit-base-patch32
CLUSTER_THRESHOLD=0.72
MAX_IMAGE_SIZE=1024

# VLM
GEMINI_API_KEY=your_production_api_key
VLM_ENABLED=true
VLM_TIMEOUT=5
VLM_FALLBACK_TO_CLIP=true

# Security
API_KEY=your_secure_production_api_key
ALLOWED_ORIGINS=https://app.example.com

# Observability
METRICS_ENABLED=true
TRACING_ENABLED=false
```

## Configuration Validation

The application validates configuration on startup. Check logs for errors:

```bash
# Check for configuration errors
docker-compose logs app | grep -i "error\|warning"
```

## Environment File Location

By default, configuration is loaded from:

1. `.env` file in project root
2. Environment variables (override `.env`)

**Priority:** Environment variables > .env file > defaults

## Configuration Best Practices

1. **Never commit secrets** to version control
2. **Use different configs** for dev/staging/production
3. **Set LOG_LEVEL=INFO** in production (not DEBUG)
4. **Enable METRICS_ENABLED** in production
5. **Use Redis queue** for distributed deployments
6. **Set appropriate DB_POOL_SIZE** based on load
7. **Configure CORS** restrictively in production
8. **Use strong API_KEY** if enabling authentication
9. **Monitor resource limits** with health endpoints
