# Troubleshooting Guide

Common issues and their solutions.

## Table of Contents

1. [Application Won't Start](#application-wont-start)
2. [Database Connection Issues](#database-connection-issues)
3. [Storage Issues](#storage-issues)
4. [Worker/Queue Issues](#workerqueue-issues)
5. [Performance Problems](#performance-problems)
6. [VLM API Issues](#vlm-api-issues)
7. [Monitoring Issues](#monitoring-issues)
8. [Memory/Resource Issues](#memoryresource-issues)

---

## Application Won't Start

### Symptom

Application container exits immediately or won't start.

### Diagnostic Steps

1. **Check logs:**

```bash
docker-compose logs app
```

2. **Check health:**

```bash
curl http://localhost:8000/live
```

3. **Check dependencies:**

```bash
docker-compose ps
```

### Common Causes & Solutions

#### Missing Environment Variables

**Error:** `KeyError` or `ValidationError` in logs

**Solution:** Ensure all required environment variables are set:

```bash
# Check .env file exists
cat .env

# Verify database URL
echo $DATABASE_URL
```

#### Database Not Ready

**Error:** `could not connect to server` or `Connection refused`

**Solution:** Wait for database to be ready:

```bash
# Check database health
docker-compose exec postgres pg_isready -U postgres

# Restart app after database is ready
docker-compose restart app
```

#### Port Already in Use

**Error:** `Address already in use`

**Solution:** Change port or stop conflicting service:

```bash
# Change port in docker-compose.yml
ports:
  - "8001:8000"  # Use different external port

# Or stop conflicting service
lsof -i :8000
kill <PID>
```

---

## Database Connection Issues

### Symptom

Application can't connect to database or queries fail.

### Diagnostic Steps

1. **Check database health:**

```bash
docker-compose exec postgres pg_isready -U postgres
```

2. **Test connection:**

```bash
docker-compose exec postgres psql -U postgres -d file_allocator -c "SELECT 1;"
```

3. **Check connection pool:**

```bash
curl http://localhost:8000/health | jq '.database'
```

### Common Causes & Solutions

#### Connection Pool Exhausted

**Symptom:** Slow queries, timeouts

**Solution:** Increase pool size:

```env
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40
```

#### Too Many Connections

**Error:** `FATAL: sorry, too many clients already`

**Solution:** Reduce pool size or increase PostgreSQL max_connections:

```sql
-- In PostgreSQL
ALTER SYSTEM SET max_connections = 200;
SELECT pg_reload_conf();
```

#### pgvector Extension Missing

**Error:** `extension "vector" does not exist`

**Solution:** Install pgvector extension:

```bash
docker-compose exec postgres psql -U postgres -d file_allocator -c "CREATE EXTENSION vector;"
```

#### Migration Not Applied

**Error:** Table/column doesn't exist

**Solution:** Run migrations:

```bash
docker-compose exec app python scripts/migrate.py
```

---

## Storage Issues

### Symptom

Can't upload files, retrieve files, or storage backend errors.

### Diagnostic Steps

1. **Check storage health:**

```bash
curl http://localhost:8000/health | jq '.storage'
```

2. **Check storage backend config:**

```bash
docker-compose exec app env | grep STORAGE
```

3. **Test storage access:**

```bash
# For filesystem
docker-compose exec app ls -la /app/storage
```

### Common Causes & Solutions

#### Filesystem Permission Denied

**Error:** `PermissionError: [Errno 13]`

**Solution:** Fix permissions:

```bash
# On host
chmod -R 777 ./storage

# Or in docker-compose.yml
volumes:
  - ./storage:/app/storage:rw
```

---

## Worker/Queue Issues

### Symptom

Jobs not processing, queue backing up, workers crashed.

### Diagnostic Steps

1. **Check worker health:**

```bash
curl http://localhost:8000/health | jq '.workers'
```

2. **Check queue depth:**

```bash
curl http://localhost:8000/metrics | grep queue_depth
```

3. **Check dead letter queue:**

```bash
curl http://localhost:8000/api/v1/admin/dlq
```

### Common Causes & Solutions

#### Workers Not Running

**Symptom:** Jobs queued but not processing

**Solution:** Restart application:

```bash
docker-compose restart app

# Check worker count
curl http://localhost:8000/health | jq '.workers.num_workers'
```

#### Queue Depth Growing

**Symptom:** `queue_depth` metric increasing

**Solution:** Increase worker threads:

```env
WORKER_THREADS=8  # Increase based on CPU cores
```

#### Jobs Failing Repeatedly

**Symptom:** High dead letter queue depth

**Solution:** Check DLQ for errors:

```bash
# List failed jobs
curl http://localhost:8000/api/v1/admin/dlq | jq '.[] | {job_id, error}'

# Get specific job details
curl http://localhost:8000/api/v1/admin/dlq/{job_id}
```

#### Redis Connection Failed (when using Redis queue)

**Error:** `ConnectionError: Error connecting to Redis`

**Solution:** Check Redis health:

```bash
# Test Redis
docker-compose exec redis redis-cli ping

# Check Redis URL
echo $REDIS_URL
```

---

## Performance Problems

### Symptom

Slow response times, high latency, timeouts.

### Diagnostic Steps

1. **Check metrics:**

```bash
# API latency
curl http://localhost:8000/metrics | grep ingest_latency

# Job processing duration
curl http://localhost:8000/metrics | grep job_processing_duration

# Search latency
curl http://localhost:8000/metrics | grep search_latency
```

2. **Check system resources:**

```bash
curl http://localhost:8000/health | jq '.system'
```

3. **Check Prometheus:**
   Go to http://localhost:9090 and run:

```promql
histogram_quantile(0.95, rate(job_processing_duration_seconds_bucket[5m]))
```

### Common Causes & Solutions

#### High CPU Usage

**Symptom:** CPU > 80%, slow processing

**Solution:**

- Reduce worker threads
- Enable rate limiting
- Scale horizontally

```env
WORKER_THREADS=4  # Reduce if CPU-bound
```

#### High Memory Usage

**Symptom:** Memory > 2GB, possible OOM

**Solution:**

- Process smaller batches
- Reduce image sizes
- Add memory limits

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          memory: 4G
```

#### Slow Database Queries

**Symptom:** High `db_query_duration_seconds`

**Solution:**

- Add indexes
- Optimize queries
- Increase connection pool

```sql
-- Check slow queries
SELECT * FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;

-- Add indexes
CREATE INDEX idx_media_clusters_embedding ON media_clusters USING ivfflat (embedding vector_cosine_ops);
```

#### Embedding Generation Slow

**Symptom:** High job processing time for media

**Solution:**

- Use smaller CLIP model
- Enable GPU if available
- Batch processing

```env
EMBEDDING_MODEL=openai/clip-vit-base-patch16  # Smaller model
```

---

## VLM API Issues

### Symptom

VLM analysis failing, rate limit errors, timeouts.

### Diagnostic Steps

1. **Check VLM config:**

```bash
docker-compose exec app env | grep VLM
docker-compose exec app env | grep GEMINI
```

2. **Check error rate:**

```bash
curl http://localhost:8000/metrics | grep jobs_processed_total
```

3. **Check logs:**

```bash
docker-compose logs app | grep -i vlm
```

### Common Causes & Solutions

#### Invalid API Key

**Error:** `401 Unauthorized` or `InvalidApiKey`

**Solution:** Verify API key:

```env
GEMINI_API_KEY=your_valid_api_key
```

#### Rate Limiting

**Error:** `429 Too Many Requests` or `ResourceExhausted`

**Solution:** Enable fallback and reduce rate:

```env
VLM_FALLBACK_TO_CLIP=true
VLM_TIMEOUT=10  # Increase timeout
```

Or implement backoff in code (already implemented with retries).

#### VLM Timeout

**Error:** `TimeoutError` or request taking too long

**Solution:** Increase timeout:

```env
VLM_TIMEOUT=10  # Increase from default 5
```

#### VLM Disabled

**Symptom:** No VLM analysis happening

**Solution:** Enable VLM:

```env
VLM_ENABLED=true
VLM_FALLBACK_TO_CLIP=true
```

---

## Monitoring Issues

### Symptom

Prometheus not scraping, Grafana not showing data, metrics missing.

### Diagnostic Steps

1. **Check Prometheus targets:**
   Go to http://localhost:9090/targets

2. **Check metrics endpoint:**

```bash
curl http://localhost:8000/metrics
```

3. **Check Prometheus config:**

```bash
docker-compose exec prometheus cat /etc/prometheus/prometheus.yml
```

### Common Causes & Solutions

#### Metrics Disabled

**Solution:** Enable metrics:

```env
METRICS_ENABLED=true
```

#### Prometheus Can't Reach App

**Error:** Target down in Prometheus

**Solution:** Check network and endpoint:

```bash
# From Prometheus container
docker-compose exec prometheus wget -O- http://app:8000/metrics

# Check Docker network
docker network inspect mammothbox_app_network
```

#### Grafana No Data

**Symptom:** Dashboards empty

**Solution:**

1. Verify Prometheus datasource: http://localhost:3000/datasources
2. Test query in Prometheus first
3. Check time range in Grafana

#### Alerts Not Firing

**Solution:** Enable alert rules:

```yaml
# In prometheus.yml
rule_files:
  - "alerts.yml"
```

---

## Memory/Resource Issues

### Symptom

Out of memory, container crashed, high resource usage.

### Diagnostic Steps

1. **Check resource usage:**

```bash
docker stats

curl http://localhost:8000/health | jq '.system'
```

2. **Check logs for OOM:**

```bash
docker-compose logs app | grep -i "memory\|oom"
```

### Common Causes & Solutions

#### Container Out of Memory

**Error:** Container exits with code 137

**Solution:** Increase memory limit:

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G
```

#### Memory Leak

**Symptom:** Memory usage growing over time

**Solution:**

- Check for unclosed file handles
- Monitor with profiler
- Restart periodically (temporary)

```bash
# Restart on high memory
if [ $(curl -s http://localhost:8000/health | jq '.system.memory_rss_mb') -gt 2000 ]; then
  docker-compose restart app
fi
```

#### Disk Space Full

**Error:** `No space left on device`

**Solution:** Clean up storage:

```bash
# Clean up Docker
docker system prune -a

# Clean up application storage
docker-compose exec app du -sh /app/storage/*
docker-compose exec app find /app/storage -type f -mtime +30 -delete
```

---

## Getting Help

If issues persist:

1. **Collect diagnostics:**

```bash
# Save logs
docker-compose logs > logs.txt

# Save health check
curl http://localhost:8000/health > health.json

# Save metrics
curl http://localhost:8000/metrics > metrics.txt
```

2. **Check documentation:**

- [Deployment Guide](./DEPLOYMENT_GUIDE.md)
- [Configuration Reference](./CONFIGURATION.md)
- [Technical Specification](./technical_specification.md)

3. **Enable debug logging:**

```env
DEBUG=true
LOG_LEVEL=DEBUG
```

4. **Open an issue** with:

- Environment details
- Steps to reproduce
- Logs and error messages
- Configuration (sanitized)
