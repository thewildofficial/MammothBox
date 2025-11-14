"""
FastAPI middleware for request tracking and observability.

Provides:
- Request ID generation and propagation
- Request/response logging
- Performance tracking
"""

import time
import logging
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.common.logging_config import set_request_id, clear_request_id

logger = logging.getLogger(__name__)


class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track requests with correlation IDs.

    Adds X-Request-ID header and logs request/response.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with tracking."""
        # Get or generate request ID
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = set_request_id()
        else:
            set_request_id(request_id)

        # Log request
        logger.info(
            "Incoming request",
            extra={
                "extra_fields": {
                    "method": request.method,
                    "path": request.url.path,
                    "client": request.client.host if request.client else None,
                    "request_id": request_id,
                }
            },
        )

        # Track timing
        start_time = time.time()

        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            logger.error(
                "Request failed",
                extra={
                    "extra_fields": {
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "request_id": request_id,
                    }
                },
            )
            raise
        finally:
            clear_request_id()

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        # Log response
        logger.info(
            "Request completed",
            extra={
                "extra_fields": {
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "request_id": request_id,
                }
            },
        )

        return response
