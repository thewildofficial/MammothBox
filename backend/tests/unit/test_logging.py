"""
Unit tests for structured logging.
"""

import pytest
import json
import logging
from io import StringIO

from src.common.logging_config import (
    StructuredFormatter,
    RequestLogger,
    PerformanceTracker,
    get_request_id,
    set_request_id,
    setup_logging,
)


class TestStructuredFormatter:
    """Tests for StructuredFormatter class."""

    def test_format_creates_json(self):
        """Formatter should create JSON log records."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)
        parsed = json.loads(formatted)

        assert parsed["message"] == "Test message"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert "timestamp" in parsed

    def test_format_includes_request_id(self):
        """Formatter should include request_id if present."""
        set_request_id("test-req-123")

        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)
        parsed = json.loads(formatted)

        assert parsed["request_id"] == "test-req-123"

    def test_format_handles_extra_fields(self):
        """Formatter should include extra fields."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.user_id = "user123"
        record.action = "upload"

        formatted = formatter.format(record)
        parsed = json.loads(formatted)

        assert parsed["user_id"] == "user123"
        assert parsed["action"] == "upload"

    def test_format_handles_exception(self):
        """Formatter should include exception info."""
        formatter = StructuredFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

            record = logging.LogRecord(
                name="test.logger",
                level=logging.ERROR,
                pathname="test.py",
                lineno=42,
                msg="Error occurred",
                args=(),
                exc_info=exc_info,
            )

            formatted = formatter.format(record)
            parsed = json.loads(formatted)

            assert "exception" in parsed
            assert "ValueError: Test error" in parsed["exception"]


class TestRequestLogger:
    """Tests for RequestLogger class."""

    def test_log_creates_record_with_request_id(self):
        """RequestLogger should add request_id to log records."""
        set_request_id("req-456")

        logger = RequestLogger("test.logger")
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("Test log message")

        output = stream.getvalue()
        parsed = json.loads(output.strip())

        assert parsed["request_id"] == "req-456"
        assert parsed["message"] == "Test log message"


class TestPerformanceTracker:
    """Tests for PerformanceTracker context manager."""

    def test_tracks_operation_duration(self, caplog):
        """PerformanceTracker should log operation duration."""
        caplog.set_level(logging.INFO)

        with PerformanceTracker("test_operation"):
            pass  # Simulated work

        # Check log was created
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert "test_operation" in record.getMessage()
        assert "completed in" in record.getMessage()

    def test_tracks_with_metadata(self, caplog):
        """PerformanceTracker should include metadata."""
        caplog.set_level(logging.INFO)

        with PerformanceTracker("upload", metadata={"file_size": 1024}):
            pass

        record = caplog.records[0]
        assert hasattr(record, 'file_size')
        assert record.file_size == 1024


class TestRequestIdContext:
    """Tests for request ID context management."""

    def test_set_and_get_request_id(self):
        """Should set and retrieve request ID."""
        set_request_id("ctx-test-789")
        assert get_request_id() == "ctx-test-789"

    def test_get_request_id_default(self):
        """Should return None when no request ID set."""
        # Clear any existing
        set_request_id(None)
        assert get_request_id() is None


class TestLoggingSetup:
    """Tests for logging setup function."""

    def test_setup_logging_json_format(self):
        """setup_logging should configure JSON format."""
        setup_logging(level="INFO", format_type="json")

        logger = logging.getLogger("test.setup")

        # Should have handlers
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0

    def test_setup_logging_text_format(self):
        """setup_logging should configure text format."""
        setup_logging(level="DEBUG", format_type="text")

        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0
        assert root_logger.level == logging.DEBUG


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
