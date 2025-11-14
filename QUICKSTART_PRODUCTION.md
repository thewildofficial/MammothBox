# Quick Start: Production Features

Get up and running with Phase 9 production features in 5 minutes.

## Step 1: Install Dependencies (1 min)

```bash
pip install -r requirements.txt
```

New dependencies include:

- `prometheus-client` - Metrics
- `tenacity` - Retry logic
- `psutil` - System monitoring
- `opentelemetry` packages - Tracing (optional)

## Step 2: Start Full Stack (2 min)

```bash
# Start all services
docker-compose up -d

# Check all services are running
docker-compose ps

# Should see:
# - postgres (database)
# - redis (queue)
# - app (API server)
# - prometheus (metrics)
# - grafana (dashboards)
```

## Step 3: Verify Health (30 sec)

```bash
# Quick health check
curl http://localhost:8000/health | jq

# Expected output:
# {
#   "status": "healthy",
#   "database": { "status": "healthy" },
#   "workers": { "status": "healthy" },
#   "storage": { "status": "healthy" },
#   "system": { "cpu_percent": 12.3, "memory_rss_mb": 234.5 }
# }
```

## Step 4: Check Monitoring (1 min)

### Prometheus

Open http://localhost:9090

Try these queries:

```promql
# Request rate
rate(ingest_requests_total[5m])

# Job processing time (P95)
histogram_quantile(0.95, rate(job_processing_duration_seconds_bucket[5m]))
```

### Grafana

Open http://localhost:3000

- Username: `admin`
- Password: `admin`

Prometheus datasource is pre-configured.

### API Documentation

Open http://localhost:8000/api/docs

Interactive API explorer with all endpoints.

## Step 5: Test Upload (30 sec)

```bash
# Upload test image
curl -X POST http://localhost:8000/api/v1/ingest/media \
  -F "files=@/path/to/image.jpg" \
  -F "request_id=test_123"

# Check metrics
curl http://localhost:8000/metrics | grep ingest_requests_total

# Check logs
docker-compose logs app --tail=50
```

## Key Endpoints

| Endpoint            | Purpose                    |
| ------------------- | -------------------------- |
| `/health`           | Comprehensive health check |
| `/ready`            | Kubernetes readiness probe |
| `/live`             | Kubernetes liveness probe  |
| `/metrics`          | Prometheus metrics         |
| `/api/docs`         | Interactive API docs       |
| `/api/v1/admin/dlq` | Dead letter queue          |

## View Logs

```bash
# Follow logs (JSON format in production)
docker-compose logs -f app

# Filter by level
docker-compose logs app | jq 'select(.level=="ERROR")'

# Filter by request ID
docker-compose logs app | jq 'select(.request_id=="550e8400-e29b-41d4-a716-446655440000")'
```

## Check Metrics

```bash
# Get all metrics
curl http://localhost:8000/metrics

# Check specific metrics
curl http://localhost:8000/metrics | grep -E "ingest_requests_total|queue_depth|job_processing"
```

## Test Resilience

### Circuit Breaker

```python
from src.common.resilience import get_circuit_breaker

# Get circuit breaker
breaker = get_circuit_breaker("test_service")

# Use it
result = breaker.call(some_function, arg1, arg2)
```

### Retry Logic

```python
from src.common.resilience import retry_database_operation

@retry_database_operation
def query_database():
    # Automatically retried 3 times with exponential backoff
    pass
```

### Dead Letter Queue

```bash
# List failed jobs
curl http://localhost:8000/api/v1/admin/dlq

# Get specific job
curl http://localhost:8000/api/v1/admin/dlq/{job_id}
```

## Configuration

### Development (default)

```env
DEBUG=true
LOG_LEVEL=DEBUG
STORAGE_BACKEND=fs://
QUEUE_BACKEND=inproc
```

### Production

```env
DEBUG=false
LOG_LEVEL=INFO
STORAGE_BACKEND=fs://
STORAGE_PATH=/app/storage
QUEUE_BACKEND=redis
REDIS_URL=redis://redis:6379/0
METRICS_ENABLED=true
```

## Performance Testing

```bash
# Run performance tests
python scripts/test_performance.py

# Tests:
# - 100 concurrent uploads
# - Search under load
# - P95/P99 latency
```

## Troubleshooting

### Service won't start

```bash
# Check logs
docker-compose logs app

# Check dependencies
docker-compose ps

# Restart
docker-compose restart app
```

### High latency

```bash
# Check system resources
curl http://localhost:8000/health | jq '.system'

# Check queue depth
curl http://localhost:8000/metrics | grep queue_depth

# Check Prometheus
open http://localhost:9090
# Query: histogram_quantile(0.95, rate(job_processing_duration_seconds_bucket[5m]))
```

### Jobs failing

```bash
# Check DLQ
curl http://localhost:8000/api/v1/admin/dlq

# Check error logs
docker-compose logs app | jq 'select(.level=="ERROR")'
```

## Next Steps

1. **Read documentation:**

   - `docs/DEPLOYMENT_GUIDE.md` - Full deployment guide
   - `docs/CONFIGURATION.md` - All config options
   - `docs/TROUBLESHOOTING.md` - Common issues

2. **Set up dashboards:**

   - Create Grafana dashboards for key metrics
   - Configure alert notifications

3. **Configure production:**

   - Configure Redis for distributed queue
   - Set secure API keys
   - Enable TLS/SSL

4. **Test performance:**
   - Run load tests
   - Verify SLO targets
   - Tune worker threads

## Monitoring Checklist

Daily checks:

- [ ] Check `/health` endpoint
- [ ] Review error logs
- [ ] Check DLQ depth
- [ ] Review Prometheus alerts
- [ ] Check system resources

Weekly checks:

- [ ] Review performance metrics
- [ ] Analyze slow queries
- [ ] Check storage usage
- [ ] Review alert history

## Support

Questions? Check:

1. Documentation in `docs/`
2. Troubleshooting guide
3. Application logs
4. Prometheus metrics
5. Dead letter queue

---

**You're ready for production! 🚀**

All Phase 9 features are active and ready to use.
