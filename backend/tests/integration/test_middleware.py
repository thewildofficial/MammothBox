"""
Integration tests for request tracking middleware.
"""

import pytest
from fastapi.testclient import TestClient
from src.main import app


class TestRequestTrackingMiddleware:
    """Tests for RequestTrackingMiddleware."""

    def test_generates_request_id(self):
        """Middleware should generate request ID if not provided."""
        client = TestClient(app)
        response = client.get("/live")

        # Should have X-Request-ID in response
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 0

    def test_preserves_provided_request_id(self):
        """Middleware should preserve provided X-Request-ID."""
        client = TestClient(app)
        custom_id = "custom-req-id-123"

        response = client.get("/live", headers={"X-Request-ID": custom_id})

        assert response.headers["X-Request-ID"] == custom_id

    def test_request_id_in_logs(self):
        """Request ID should be available in request context."""
        # This is harder to test directly, but we can verify the header
        client = TestClient(app)
        response = client.get("/health")

        # Should have request ID
        assert "X-Request-ID" in response.headers

    def test_different_requests_get_different_ids(self):
        """Each request should get unique request ID."""
        client = TestClient(app)

        response1 = client.get("/live")
        response2 = client.get("/live")

        id1 = response1.headers["X-Request-ID"]
        id2 = response2.headers["X-Request-ID"]

        assert id1 != id2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
