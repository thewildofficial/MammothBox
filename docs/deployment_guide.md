# Production Deployment Guide

## Overview

This guide covers deploying the File Allocator API to production with full observability and monitoring.

## Prerequisites

- Docker and Docker Compose
- At least 4GB RAM
- PostgreSQL with pgvector extension
- (Optional) Redis for distributed queue

## Quick Start with Docker Compose

### 1. Environment Configuration

Create a `.env` file in the project root:

```env
# Database
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/file_allocator
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# Storage Backend
STORAGE_BACKEND=fs://
STORAGE_PATH=/app/storage

# Application
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=false
LOG_LEVEL=INFO

# Workers
WORKER_THREADS=4
QUEUE_BACKEND=inproc  # or redis
REDIS_URL=redis://redis:6379/0

# Media Processing
EMBEDDING_MODEL=openai/clip-vit-base-patch32
CLUSTER_THRESHOLD=0.72

# VLM Configuration
GEMINI_API_KEY=your_gemini_api_key
VLM_ENABLED=true
VLM_FALLBACK_TO_CLIP=true

# Observability
METRICS_ENABLED=true
TRACING_ENABLED=false
```

### 2. Start Services

```bash
# Start all services
docker-compose up -d

# Check service health
docker-compose ps

# View logs
docker-compose logs -f app
```

### 3. Access Endpoints

- **API Documentation**: http://localhost:8000/api/docs
- **Health Check**: http://localhost:8000/health
- **Metrics**: http://localhost:8000/metrics
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)

## Health Checks

The application provides multiple health endpoints:

### Liveness Probe

```bash
curl http://localhost:8000/live
```

Returns 200 if the application process is alive.

### Readiness Probe

```bash
curl http://localhost:8000/ready
```

Returns 200 if the application is ready to serve traffic (database, storage, workers are healthy).

### Detailed Health

```bash
curl http://localhost:8000/health
```

Returns detailed status of all components including resource usage.

## Monitoring Setup

### Prometheus

Prometheus scrapes metrics from `/metrics` every 15 seconds.

Access Prometheus UI: http://localhost:9090

Example queries:

```promql
# Request rate
rate(ingest_requests_total[5m])

# P95 latency
histogram_quantile(0.95, rate(job_processing_duration_seconds_bucket[5m]))

# Queue depth
queue_depth

# Error rate
rate(jobs_processed_total{status="failure"}[5m])
```

### Grafana

Access Grafana: http://localhost:3000

- Default credentials: admin/admin
- Prometheus datasource is pre-configured

Key dashboards to create:

1. **Overview**: Request rate, latency, error rate
2. **Job Processing**: Queue depth, processing time, worker status
3. **Database**: Connection pool, query performance
4. **System**: CPU, memory, disk usage

### Alert Rules

Alerts are defined in `monitoring/alerts.yml`:

- Dead letter queue depth > 10
- P95 job latency > 10s
- P95 search latency > 500ms
- Database connection pool exhaustion
- Worker crash rate > 5%
- VLM API failure rate > 20%

## Storage Backends

### Filesystem (Development)

```env
STORAGE_BACKEND=fs://
STORAGE_PATH=/app/storage
```

## Performance Tuning

### Database Connection Pool

```env
DB_POOL_SIZE=20        # Max connections
DB_MAX_OVERFLOW=40     # Additional overflow connections
```

### Worker Threads

```env
WORKER_THREADS=8       # Number of worker threads (adjust based on CPU cores)
```

### Queue Backend

For distributed deployment:

```env
QUEUE_BACKEND=redis
REDIS_URL=redis://redis:6379/0
```

## Scaling

### Horizontal Scaling

Run multiple app instances behind a load balancer:

```bash
docker-compose up --scale app=3
```

Ensure:

- Use Redis for queue backend (not in-process)
- Database connection pool is sized appropriately

### Vertical Scaling

Increase resources for individual services:

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: "4"
          memory: 8G
        reservations:
          cpus: "2"
          memory: 4G
```

## Troubleshooting

### Check Application Logs

```bash
# Structured JSON logs in production
docker-compose logs -f app

# Filter by level
docker-compose logs app | jq 'select(.level=="ERROR")'
```

### Check Dead Letter Queue

```bash
# List failed jobs
curl http://localhost:8000/api/v1/admin/dlq

# Get specific job
curl http://localhost:8000/api/v1/admin/dlq/{job_id}
```

### Database Connection Issues

```bash
# Check database health
docker-compose exec postgres pg_isready -U postgres

# Check connection pool
curl http://localhost:8000/health | jq '.database'
```

### Worker Issues

```bash
# Check worker status
curl http://localhost:8000/health | jq '.workers'

# View worker metrics
curl http://localhost:8000/metrics | grep active_workers
```

## Security

### API Key Authentication

Set API key in environment:

```env
API_KEY=your_secure_api_key_here
```

Then include in requests:

```bash
curl -H "X-API-Key: your_secure_api_key_here" http://localhost:8000/api/v1/ingest
```

### CORS Configuration

```env
ALLOWED_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
```

### Secrets Management

Use Docker secrets or external secret managers:

```yaml
services:
  app:
    secrets:
      - db_password
      - gemini_api_key

secrets:
  db_password:
    external: true
  gemini_api_key:
    external: true
```

## Backup and Recovery

### Database Backup

```bash
# Backup
docker-compose exec postgres pg_dump -U postgres file_allocator > backup.sql

# Restore
docker-compose exec -T postgres psql -U postgres file_allocator < backup.sql
```

### Storage Backup

For filesystem:

```bash
tar -czf storage-backup.tar.gz ./storage
```

## Performance Targets

Per technical specification:

- **API Latency (P95)**: < 200ms for ingest acknowledgment
- **Processing Latency (P95)**:
  - Images: < 1.5s
  - Videos: < 5s
- **Search Latency (P95)**: < 150ms
- **Throughput**:
  - 100 requests/sec (ingest ack)
  - 10-20 assets/sec (processing)

Monitor these metrics in Prometheus/Grafana.

## Support

For issues:

1. Check logs: `docker-compose logs -f app`
2. Check health: `curl http://localhost:8000/health`
3. Check metrics: http://localhost:9090
4. Check DLQ: `curl http://localhost:8000/api/v1/admin/dlq`
