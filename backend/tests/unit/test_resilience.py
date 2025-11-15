"""
Unit tests for resilience utilities (retry, circuit breaker, fallback).
"""

import time
import pytest
from unittest.mock import Mock, patch

from src.common.resilience import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
    get_circuit_breaker,
    retry_database_operation,
    retry_storage_operation,
    retry_embedding_generation,
    retry_vlm_call,
    with_fallback,
)


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    def test_circuit_breaker_starts_closed(self):
        """Circuit breaker should start in CLOSED state."""
        cb = CircuitBreaker("test", failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_circuit_breaker_success(self):
        """Successful calls should keep circuit CLOSED."""
        cb = CircuitBreaker("test", failure_threshold=3)

        def success_func():
            return "success"

        result = cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_circuit_breaker_opens_after_threshold(self):
        """Circuit should OPEN after reaching failure threshold."""
        cb = CircuitBreaker("test", failure_threshold=3)

        def failing_func():
            raise RuntimeError("Test error")

        # Trigger failures
        for _ in range(3):
            with pytest.raises(RuntimeError):
                cb.call(failing_func)

        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 3

    def test_circuit_breaker_rejects_when_open(self):
        """OPEN circuit should reject calls immediately."""
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=10)

        def failing_func():
            raise RuntimeError("Test error")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call(failing_func)

        assert cb.state == CircuitState.OPEN

        # Next call should be rejected without calling function
        with pytest.raises(CircuitBreakerError, match="is OPEN"):
            cb.call(failing_func)

    def test_circuit_breaker_half_open_after_timeout(self):
        """Circuit should try HALF_OPEN after recovery timeout."""
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)

        def failing_func():
            raise RuntimeError("Test error")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call(failing_func)

        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)

        # Next call should attempt HALF_OPEN
        with pytest.raises(RuntimeError):
            cb.call(failing_func)

        # Should still be OPEN after failed attempt
        assert cb.state == CircuitState.OPEN

    def test_circuit_breaker_closes_on_success_in_half_open(self):
        """Successful call in HALF_OPEN should CLOSE circuit."""
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)

        call_count = [0]

        def flaky_func():
            call_count[0] += 1
            if call_count[0] <= 2:
                raise RuntimeError("Failing")
            return "success"

        # Open the circuit
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call(flaky_func)

        assert cb.state == CircuitState.OPEN

        # Wait for recovery
        time.sleep(0.15)

        # Successful call should close circuit
        result = cb.call(flaky_func)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_circuit_breaker_manual_reset(self):
        """Manual reset should close circuit."""
        cb = CircuitBreaker("test", failure_threshold=2)

        def failing_func():
            raise RuntimeError("Test error")

        # Open circuit
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call(failing_func)

        assert cb.state == CircuitState.OPEN

        # Manual reset
        cb.reset()

        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_get_circuit_breaker_singleton(self):
        """get_circuit_breaker should return same instance for same name."""
        cb1 = get_circuit_breaker("test_service")
        cb2 = get_circuit_breaker("test_service")

        assert cb1 is cb2


class TestRetryDecorators:
    """Tests for retry decorators."""

    def test_retry_database_operation_success(self):
        """Successful operation should not retry."""
        call_count = [0]

        @retry_database_operation
        def db_operation():
            call_count[0] += 1
            return "success"

        result = db_operation()
        assert result == "success"
        assert call_count[0] == 1

    def test_retry_database_operation_retries_on_connection_error(self):
        """Should retry on ConnectionError."""
        call_count = [0]

        @retry_database_operation
        def db_operation():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("Database unavailable")
            return "success"

        result = db_operation()
        assert result == "success"
        assert call_count[0] == 3

    def test_retry_database_operation_fails_after_max_retries(self):
        """Should fail after max retries."""
        from tenacity import RetryError
        call_count = [0]

        @retry_database_operation
        def db_operation():
            call_count[0] += 1
            raise ConnectionError("Database unavailable")

        with pytest.raises((ConnectionError, RetryError)):
            db_operation()

        # Should have tried 3 times (initial + 2 retries = 3 total)
        assert call_count[0] == 3

    def test_retry_storage_operation(self):
        """Storage operation should retry on IOError."""
        call_count = [0]

        @retry_storage_operation
        def storage_operation():
            call_count[0] += 1
            if call_count[0] < 2:
                raise IOError("Storage unavailable")
            return "stored"

        result = storage_operation()
        assert result == "stored"
        assert call_count[0] == 2

    def test_retry_embedding_generation(self):
        """Embedding generation should retry twice."""
        call_count = [0]

        @retry_embedding_generation
        def generate_embedding():
            call_count[0] += 1
            if call_count[0] < 2:
                raise RuntimeError("Model error")
            return [0.1, 0.2, 0.3]

        result = generate_embedding()
        assert len(result) == 3
        assert call_count[0] == 2

    def test_retry_vlm_call(self):
        """VLM call should retry with longer backoff."""
        call_count = [0]

        @retry_vlm_call
        def vlm_call():
            call_count[0] += 1
            if call_count[0] < 2:
                raise ConnectionError("API unavailable")
            return {"result": "analysis"}

        result = vlm_call()
        assert result["result"] == "analysis"
        assert call_count[0] == 2


class TestFallback:
    """Tests for fallback utility."""

    def test_fallback_not_used_on_success(self):
        """Fallback should not be used if primary succeeds."""
        def primary():
            return "primary_result"

        def fallback():
            return "fallback_result"

        result, used_fallback = with_fallback(primary, fallback)
        assert result == "primary_result"
        assert used_fallback is False

    def test_fallback_used_on_failure(self):
        """Fallback should be used if primary fails."""
        def primary():
            raise RuntimeError("Primary failed")

        def fallback():
            return "fallback_result"

        result, used_fallback = with_fallback(primary, fallback)
        assert result == "fallback_result"
        assert used_fallback is True

    def test_fallback_with_arguments(self):
        """Fallback should work with function arguments."""
        def primary(x, y):
            raise RuntimeError("Primary failed")

        def fallback(x, y):
            return x + y

        result, used_fallback = with_fallback(primary, fallback, 5, 3)
        assert result == 8
        assert used_fallback is True

    def test_fallback_with_kwargs(self):
        """Fallback should work with keyword arguments."""
        def primary(a, b=10):
            raise RuntimeError("Primary failed")

        def fallback(a, b=10):
            return a * b

        result, used_fallback = with_fallback(primary, fallback, 5, b=2)
        assert result == 10
        assert used_fallback is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
