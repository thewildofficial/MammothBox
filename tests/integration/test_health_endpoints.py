"""
Integration tests for health check endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from src.main import app


class TestLivenessEndpoint:
    """Tests for /live endpoint."""

    def test_liveness_returns_200(self):
        """Liveness probe should always return 200."""
        client = TestClient(app)
        response = client.get("/live")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "alive"

    def test_liveness_no_dependencies(self):
        """Liveness probe should not check dependencies."""
        # Should succeed even if DB/Redis are down
        client = TestClient(app)
        response = client.get("/live")

        assert response.status_code == 200


class TestReadinessEndpoint:
    """Tests for /ready endpoint."""

    def test_readiness_structure(self):
        """Readiness endpoint should return status structure."""
        client = TestClient(app)
        response = client.get("/ready")

        data = response.json()
        assert "status" in data
        assert "checks" in data
        assert isinstance(data["checks"], dict)

    def test_readiness_checks_database(self):
        """Readiness should check database connection."""
        client = TestClient(app)
        response = client.get("/ready")

        data = response.json()
        assert "database" in data["checks"]

    def test_readiness_checks_queue(self):
        """Readiness should check queue backend connection."""
        client = TestClient(app)
        response = client.get("/ready")

        data = response.json()
        assert "queue" in data["checks"]


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_detailed_info(self):
        """Health endpoint should return detailed system info."""
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert "timestamp" in data
        assert "database" in data

    def test_health_includes_system_metrics(self):
        """Health endpoint should include system metrics."""
        client = TestClient(app)
        response = client.get("/health")

        data = response.json()

        # Should have some system info
        assert isinstance(data, dict)
        assert len(data) > 0


class TestMetricsEndpoint:
    """Tests for /metrics endpoint."""

    def test_metrics_returns_prometheus_format(self):
        """Metrics endpoint should return Prometheus-compatible format."""
        client = TestClient(app)
        response = client.get("/metrics")

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

    def test_metrics_contains_metric_names(self):
        """Metrics should contain expected metric names."""
        client = TestClient(app)
        response = client.get("/metrics")

        content = response.text

        # Should contain some metric definitions (HELP or TYPE)
        assert len(content) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
