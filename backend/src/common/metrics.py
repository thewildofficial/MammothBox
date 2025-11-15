"""
Prometheus metrics for monitoring and observability.

Provides counters, histograms, and gauges for tracking:
- Ingest requests and processing
- Job queue metrics
- Search performance
- Database operations
"""

import time
from typing import Optional, Callable
from functools import wraps
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
)

# Create a global registry
REGISTRY = CollectorRegistry()

# ========== Counters ==========

# Ingest requests
ingest_requests_total = Counter(
    "ingest_requests_total",
    "Total number of ingest requests",
    ["request_type", "status"],  # json/media, success/failure
    registry=REGISTRY,
)

# Jobs processed
jobs_processed_total = Counter(
    "jobs_processed_total",
    "Total number of jobs processed",
    ["job_type", "status"],  # json/media, success/failure/retry
    registry=REGISTRY,
)

# Clusters created
clusters_created_total = Counter(
    "clusters_created_total",
    "Total number of media clusters created",
    registry=REGISTRY,
)

# Search queries
search_queries_total = Counter(
    "search_queries_total",
    "Total number of search queries",
    ["search_type", "status"],  # text/media, success/failure
    registry=REGISTRY,
)

# ========== Histograms ==========

# Ingest latency
ingest_latency_seconds = Histogram(
    "ingest_latency_seconds",
    "Time to acknowledge ingest request",
    ["request_type"],  # json/media
    buckets=(0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0),
    registry=REGISTRY,
)

# Job processing duration
job_processing_duration_seconds = Histogram(
    "job_processing_duration_seconds",
    "Time to process a job",
    ["job_type"],  # json/media
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
    registry=REGISTRY,
)

# Search latency
search_latency_seconds = Histogram(
    "search_latency_seconds",
    "Time to execute search query",
    ["search_type"],  # text/media
    buckets=(0.01, 0.05, 0.1, 0.15, 0.2, 0.5, 1.0, 2.0),
    registry=REGISTRY,
)

# Database query duration
db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query execution time",
    ["operation"],  # insert/select/update/delete
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
    registry=REGISTRY,
)

# ========== Gauges ==========

# Queue depth
queue_depth = Gauge(
    "queue_depth",
    "Number of jobs waiting in queue",
    ["job_type"],  # json/media
    registry=REGISTRY,
)

# Active workers
active_workers = Gauge(
    "active_workers",
    "Number of active worker threads",
    registry=REGISTRY,
)

# Database connections
database_connections = Gauge(
    "database_connections",
    "Number of active database connections",
    ["state"],  # active/idle
    registry=REGISTRY,
)

# Dead letter queue depth
dead_letter_queue_depth = Gauge(
    "dead_letter_queue_depth",
    "Number of permanently failed jobs",
    ["job_type"],
    registry=REGISTRY,
)


# ========== Metric Decorators ==========

def track_ingest_time(request_type: str):
    """
    Decorator to track ingest request latency.

    Args:
        request_type: Type of request (json/media)
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "failure"
                raise e
            finally:
                duration = time.time() - start_time
                ingest_latency_seconds.labels(
                    request_type=request_type).observe(duration)
                ingest_requests_total.labels(
                    request_type=request_type, status=status).inc()

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "failure"
                raise e
            finally:
                duration = time.time() - start_time
                ingest_latency_seconds.labels(
                    request_type=request_type).observe(duration)
                ingest_requests_total.labels(
                    request_type=request_type, status=status).inc()

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def track_job_processing(job_type: str):
    """
    Decorator to track job processing duration.

    Args:
        job_type: Type of job (json/media)
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "failure"
                raise e
            finally:
                duration = time.time() - start_time
                job_processing_duration_seconds.labels(
                    job_type=job_type).observe(duration)
                jobs_processed_total.labels(
                    job_type=job_type, status=status).inc()

        return wrapper
    return decorator


def track_search_time(search_type: str):
    """
    Decorator to track search query latency.

    Args:
        search_type: Type of search (text/media)
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "failure"
                raise e
            finally:
                duration = time.time() - start_time
                search_latency_seconds.labels(
                    search_type=search_type).observe(duration)
                search_queries_total.labels(
                    search_type=search_type, status=status).inc()

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "failure"
                raise e
            finally:
                duration = time.time() - start_time
                search_latency_seconds.labels(
                    search_type=search_type).observe(duration)
                search_queries_total.labels(
                    search_type=search_type, status=status).inc()

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def track_db_query(operation: str):
    """
    Decorator to track database query duration.

    Args:
        operation: Type of operation (insert/select/update/delete)
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                db_query_duration_seconds.labels(
                    operation=operation).observe(duration)

        return wrapper
    return decorator


def get_metrics() -> bytes:
    """
    Get current metrics in Prometheus format.

    Returns:
        Metrics as bytes
    """
    return generate_latest(REGISTRY)


def get_metrics_content_type() -> str:
    """Get content type for metrics response."""
    return CONTENT_TYPE_LATEST
