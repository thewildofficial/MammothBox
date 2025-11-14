"""
Structured JSON logging with correlation IDs and request tracking.

Provides production-grade logging with:
- JSON format for log aggregation
- Request correlation IDs
- Structured metadata
- Performance tracking
"""

import logging
import json
import time
import uuid
from contextvars import ContextVar
from typing import Optional, Dict, Any
from datetime import datetime

# Context variable for request ID (thread-safe)
request_id_ctx: ContextVar[Optional[str]] = ContextVar(
    "request_id", default=None)


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.

    Outputs logs in JSON format with standardized fields.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add request ID if available
        request_id = request_id_ctx.get()
        if request_id:
            log_data["request_id"] = request_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields from LoggerAdapter or extra parameter
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)


class RequestLogger:
    """
    Logger with request context and performance tracking.

    Automatically includes request_id in all log messages.
    """

    def __init__(self, logger: logging.Logger):
        """Initialize with base logger."""
        self.logger = logger

    def _log(self, level: int, msg: str, **kwargs):
        """Log with structured extra fields."""
        extra_fields = kwargs.copy()
        request_id = request_id_ctx.get()
        if request_id:
            extra_fields["request_id"] = request_id

        # Create a log record with extra fields
        record = self.logger.makeRecord(
            self.logger.name,
            level,
            "(unknown file)",
            0,
            msg,
            (),
            None,
        )
        record.extra_fields = extra_fields
        self.logger.handle(record)

    def debug(self, msg: str, **kwargs):
        """Log debug message with extra fields."""
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs):
        """Log info message with extra fields."""
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs):
        """Log warning message with extra fields."""
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs):
        """Log error message with extra fields."""
        self._log(logging.ERROR, msg, **kwargs)

    def critical(self, msg: str, **kwargs):
        """Log critical message with extra fields."""
        self._log(logging.CRITICAL, msg, **kwargs)


class PerformanceTracker:
    """
    Context manager for tracking operation performance.

    Usage:
        with PerformanceTracker("database_query", logger):
            # ... perform operation
            pass
    """

    def __init__(
        self,
        operation: str,
        logger: logging.Logger,
        log_level: int = logging.INFO,
        **extra_fields,
    ):
        """
        Initialize performance tracker.

        Args:
            operation: Operation name
            logger: Logger instance
            log_level: Log level for completion message
            **extra_fields: Additional structured fields
        """
        self.operation = operation
        self.logger = logger
        self.log_level = log_level
        self.extra_fields = extra_fields
        self.start_time: Optional[float] = None

    def __enter__(self):
        """Start timing."""
        self.start_time = time.time()
        request_id = request_id_ctx.get()
        extra = {"operation": self.operation, **self.extra_fields}
        if request_id:
            extra["request_id"] = request_id

        self.logger.log(
            logging.DEBUG,
            f"Starting operation: {self.operation}",
            extra={"extra_fields": extra},
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Log completion with duration."""
        duration_ms = (time.time() - self.start_time) * 1000
        request_id = request_id_ctx.get()

        extra = {
            "operation": self.operation,
            "duration_ms": round(duration_ms, 2),
            **self.extra_fields,
        }
        if request_id:
            extra["request_id"] = request_id

        if exc_type:
            extra["error"] = str(exc_val)
            extra["error_type"] = exc_type.__name__
            self.logger.error(
                f"Operation failed: {self.operation}",
                extra={"extra_fields": extra},
            )
        else:
            self.logger.log(
                self.log_level,
                f"Operation completed: {self.operation}",
                extra={"extra_fields": extra},
            )


def setup_logging(log_level: str = "INFO", json_format: bool = True):
    """
    Configure application logging.

    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON formatting if True, standard format if False
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper()))

    # Set formatter
    if json_format:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Set third-party loggers to WARNING to reduce noise
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def set_request_id(request_id: Optional[str] = None) -> str:
    """
    Set request ID in context.

    Args:
        request_id: Request ID (generated if not provided)

    Returns:
        Request ID
    """
    if request_id is None:
        request_id = str(uuid.uuid4())
    request_id_ctx.set(request_id)
    return request_id


def get_request_id() -> Optional[str]:
    """Get current request ID from context."""
    return request_id_ctx.get()


def clear_request_id():
    """Clear request ID from context."""
    request_id_ctx.set(None)


def get_structured_logger(name: str) -> RequestLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name

    Returns:
        RequestLogger instance
    """
    base_logger = logging.getLogger(name)
    return RequestLogger(base_logger)
