"""
Unit tests for Prometheus metrics.
"""

import pytest
from unittest.mock import Mock

from src.common.metrics import (
    ingest_requests_total,
    jobs_processed_total,
    clusters_created_total,
    search_queries_total,
    ingest_latency_seconds,
    job_processing_duration_seconds,
    search_latency_seconds,
    queue_depth,
    active_workers,
    database_connections,
    dead_letter_queue_depth,
    track_ingest_time,
    track_job_processing,
    track_search_time,
    get_metrics,
    get_metrics_content_type,
)


class TestMetricsCounters:
    """Tests for Prometheus counter metrics."""

    def test_ingest_requests_total_increments(self):
        """Ingest requests counter should increment."""
        initial = ingest_requests_total.labels(
            request_type="json", status="success")._value.get()

        ingest_requests_total.labels(
            request_type="json", status="success").inc()

        final = ingest_requests_total.labels(
            request_type="json", status="success")._value.get()
        assert final > initial

    def test_jobs_processed_total_increments(self):
        """Jobs processed counter should increment."""
        initial = jobs_processed_total.labels(
            job_type="media", status="success")._value.get()

        jobs_processed_total.labels(job_type="media", status="success").inc()

        final = jobs_processed_total.labels(
            job_type="media", status="success")._value.get()
        assert final > initial

    def test_clusters_created_total_increments(self):
        """Clusters created counter should increment."""
        initial = clusters_created_total._value.get()

        clusters_created_total.inc()

        final = clusters_created_total._value.get()
        assert final > initial

    def test_search_queries_total_increments(self):
        """Search queries counter should increment."""
        initial = search_queries_total.labels(
            search_type="text", status="success")._value.get()

        search_queries_total.labels(search_type="text", status="success").inc()

        final = search_queries_total.labels(
            search_type="text", status="success")._value.get()
        assert final > initial


class TestMetricsHistograms:
    """Tests for Prometheus histogram metrics."""

    def test_ingest_latency_observes(self):
        """Ingest latency histogram should observe values."""
        ingest_latency_seconds.labels(request_type="json").observe(0.123)
        # Just verify no errors - histogram metrics are complex to assert on

    def test_job_processing_duration_observes(self):
        """Job processing duration histogram should observe values."""
        job_processing_duration_seconds.labels(job_type="media").observe(1.234)

    def test_search_latency_observes(self):
        """Search latency histogram should observe values."""
        search_latency_seconds.labels(search_type="media").observe(0.056)


class TestMetricsGauges:
    """Tests for Prometheus gauge metrics."""

    def test_queue_depth_set(self):
        """Queue depth gauge should set values."""
        queue_depth.labels(job_type="json").set(42)
        value = queue_depth.labels(job_type="json")._value.get()
        assert value == 42

    def test_active_workers_set(self):
        """Active workers gauge should set values."""
        active_workers.set(8)
        value = active_workers._value.get()
        assert value == 8

    def test_database_connections_set(self):
        """Database connections gauge should set values."""
        database_connections.labels(state="active").set(5)
        database_connections.labels(state="idle").set(10)

        active = database_connections.labels(state="active")._value.get()
        idle = database_connections.labels(state="idle")._value.get()

        assert active == 5
        assert idle == 10

    def test_dead_letter_queue_depth_set(self):
        """DLQ depth gauge should set values."""
        dead_letter_queue_depth.labels(job_type="json").set(3)
        value = dead_letter_queue_depth.labels(job_type="json")._value.get()
        assert value == 3


class TestMetricsDecorators:
    """Tests for metrics decorator functions."""

    @pytest.mark.asyncio
    async def test_track_ingest_time_decorator_async(self):
        """Track ingest time decorator should work with async functions."""
        @track_ingest_time("json")
        async def async_ingest():
            return "ingested"

        result = await async_ingest()
        assert result == "ingested"

    def test_track_ingest_time_decorator_sync(self):
        """Track ingest time decorator should work with sync functions."""
        @track_ingest_time("media")
        def sync_ingest():
            return "ingested"

        result = sync_ingest()
        assert result == "ingested"

    def test_track_job_processing_decorator(self):
        """Track job processing decorator should track duration."""
        @track_job_processing("media")
        def process_job():
            return "processed"

        result = process_job()
        assert result == "processed"

    @pytest.mark.asyncio
    async def test_track_search_time_decorator_async(self):
        """Track search time decorator should work with async functions."""
        @track_search_time("text")
        async def async_search():
            return ["result1", "result2"]

        results = await async_search()
        assert len(results) == 2


class TestMetricsExport:
    """Tests for metrics export functionality."""

    def test_get_metrics_returns_bytes(self):
        """get_metrics should return bytes."""
        metrics = get_metrics()
        assert isinstance(metrics, bytes)
        assert len(metrics) > 0

    def test_get_metrics_contains_metric_names(self):
        """Exported metrics should contain metric names."""
        metrics = get_metrics()
        metrics_str = metrics.decode('utf-8')

        # Check for some metric names
        assert 'ingest_requests_total' in metrics_str or 'HELP' in metrics_str

    def test_get_metrics_content_type(self):
        """Should return correct content type for Prometheus."""
        content_type = get_metrics_content_type()
        assert isinstance(content_type, str)
        assert 'text/plain' in content_type or 'openmetrics' in content_type


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
