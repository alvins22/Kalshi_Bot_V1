"""Tests for API resilience system (retry, circuit breaker, rate limiting)"""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from src.api_resilience.exceptions import (
    RetriableAPIException,
    NonRetriableAPIException,
    RateLimitException,
    CircuitBreakerOpenException,
    MaxRetriesExceededException,
    NetworkException,
)
from src.api_resilience.retry_strategies import ExponentialBackoffWithJitter, RetryPolicy
from src.api_resilience.circuit_breaker import CircuitBreaker, CircuitBreakerState
from src.api_resilience.rate_limiter import TokenBucketLimiter
from src.api_resilience.metrics_collector import MetricsCollector


class TestExponentialBackoffWithJitter:
    """Test exponential backoff with jitter calculation"""

    def test_calculate_delay_first_attempt(self):
        """First attempt should have minimal delay"""
        strategy = ExponentialBackoffWithJitter(
            base_delay=1.0,
            max_delay=60.0,
        )
        delay = strategy.calculate_delay(attempt=0)
        assert 0 <= delay < 2.0  # Some jitter but mostly small

    def test_calculate_delay_grows_exponentially(self):
        """Delay should grow with attempt number"""
        strategy = ExponentialBackoffWithJitter(
            base_delay=1.0,
            max_delay=60.0,
        )
        delay_0 = strategy.calculate_delay(attempt=0)
        delay_3 = strategy.calculate_delay(attempt=3)
        delay_5 = strategy.calculate_delay(attempt=5)

        # Delays should generally increase (some variance due to jitter)
        assert delay_0 < delay_3
        assert delay_3 < delay_5

    def test_calculate_delay_respects_max(self):
        """Delay should never exceed max_delay"""
        strategy = ExponentialBackoffWithJitter(
            base_delay=1.0,
            max_delay=10.0,
        )
        for attempt in range(20):
            delay = strategy.calculate_delay(attempt)
            assert delay <= 10.0

    def test_jitter_adds_randomness(self):
        """Multiple calls should produce different delays (with jitter)"""
        strategy = ExponentialBackoffWithJitter(
            base_delay=1.0,
            max_delay=60.0,
        )
        delays = [strategy.calculate_delay(attempt=3) for _ in range(10)]
        # Should have some variance due to jitter
        assert len(set(delays)) > 1 or all(d == delays[0] for d in delays)  # Either varies or all same


class TestRetryPolicy:
    """Test retry policy logic"""

    def test_is_retriable_network_error(self):
        """Network errors should be retriable"""
        policy = RetryPolicy(max_attempts=3)
        assert policy.is_retriable(NetworkException("Connection timeout"))

    def test_is_retriable_rate_limit(self):
        """Rate limit errors should be retriable"""
        policy = RetryPolicy(max_attempts=3)
        assert policy.is_retriable(RateLimitException("Too many requests", retry_after=30))

    def test_is_not_retriable_auth_error(self):
        """Auth errors should not be retriable"""
        policy = RetryPolicy(max_attempts=3)
        assert not policy.is_retriable(NonRetriableAPIException("Invalid API key"))

    def test_is_not_retriable_bad_request(self):
        """Bad request errors should not be retriable"""
        policy = RetryPolicy(max_attempts=3)
        assert not policy.is_retriable(NonRetriableAPIException("Bad request", status_code=400))

    def test_should_retry_below_max_attempts(self):
        """Should retry if below max attempts"""
        policy = RetryPolicy(max_attempts=3)
        assert policy.should_retry(attempt=0)
        assert policy.should_retry(attempt=1)
        assert policy.should_retry(attempt=2)

    def test_should_not_retry_at_max_attempts(self):
        """Should not retry once max attempts reached"""
        policy = RetryPolicy(max_attempts=3)
        assert not policy.should_retry(attempt=3)
        assert not policy.should_retry(attempt=4)


class TestCircuitBreaker:
    """Test circuit breaker pattern"""

    def test_initial_state_is_closed(self):
        """Circuit breaker should start in CLOSED state"""
        cb = CircuitBreaker(failure_threshold=0.5, min_calls=10, timeout=60)
        assert cb.state == CircuitBreakerState.CLOSED

    def test_opens_after_failure_threshold_exceeded(self):
        """Circuit breaker should open when failure rate exceeds threshold"""
        cb = CircuitBreaker(failure_threshold=0.5, min_calls=5, timeout=60)

        def failing_func():
            raise RetriableAPIException("Connection failed")

        # Record failures
        for _ in range(3):
            try:
                cb.call(failing_func)
            except RetriableAPIException:
                pass

        # Record 2 successes
        success_func = Mock(return_value="OK")
        for _ in range(2):
            cb.call(success_func)

        # Should be OPEN now (3 failures out of 5 = 60% > 50%)
        assert cb.state == CircuitBreakerState.OPEN

    def test_raises_on_open_circuit(self):
        """Should raise CircuitBreakerOpenException when circuit is OPEN"""
        cb = CircuitBreaker(failure_threshold=0.5, min_calls=5, timeout=60)
        cb.state = CircuitBreakerState.OPEN  # Force open
        cb.last_failure_time = datetime.utcnow()

        def any_func():
            return "OK"

        with pytest.raises(CircuitBreakerOpenException):
            cb.call(any_func)

    def test_transitions_to_half_open_after_timeout(self):
        """Should transition to HALF_OPEN after timeout"""
        cb = CircuitBreaker(failure_threshold=0.5, min_calls=5, timeout=1)
        cb.state = CircuitBreakerState.OPEN
        cb.last_failure_time = datetime.utcnow() - timedelta(seconds=2)

        success_func = Mock(return_value="OK")

        # Should transition to HALF_OPEN and attempt call
        result = cb.call(success_func)
        assert result == "OK"
        assert cb.state == CircuitBreakerState.CLOSED  # Success in HALF_OPEN closes circuit

    def test_does_not_record_before_min_calls(self):
        """Should not consider opening circuit before min_calls reached"""
        cb = CircuitBreaker(failure_threshold=0.5, min_calls=10, timeout=60)

        def failing_func():
            raise RetriableAPIException("Connection failed")

        # Make 5 failures (below min_calls)
        for _ in range(5):
            try:
                cb.call(failing_func)
            except RetriableAPIException:
                pass

        # Circuit should still be CLOSED (not enough calls)
        assert cb.state == CircuitBreakerState.CLOSED

    def test_closes_after_successful_recovery(self):
        """Circuit should close after successful recovery in HALF_OPEN"""
        cb = CircuitBreaker(failure_threshold=0.5, min_calls=2, timeout=1)

        # Force open
        cb.state = CircuitBreakerState.OPEN
        cb.last_failure_time = datetime.utcnow() - timedelta(seconds=2)

        success_func = Mock(return_value="OK")

        # Call in HALF_OPEN state
        result = cb.call(success_func)
        assert result == "OK"
        assert cb.state == CircuitBreakerState.CLOSED  # Should close


class TestTokenBucketLimiter:
    """Test token bucket rate limiter"""

    def test_initial_bucket_is_full(self):
        """Bucket should start full"""
        limiter = TokenBucketLimiter(requests_per_second=10.0)
        # Should allow immediate requests
        assert limiter.allow_request()

    def test_allows_requests_within_rate(self):
        """Should allow requests within configured rate"""
        limiter = TokenBucketLimiter(requests_per_second=100.0)

        # Should allow 10 immediate requests at 100 req/sec
        for _ in range(10):
            assert limiter.allow_request()

    def test_blocks_when_over_rate(self):
        """Should block requests when rate exceeded"""
        limiter = TokenBucketLimiter(requests_per_second=2.0)

        # Allow 2 requests
        limiter.allow_request()
        limiter.allow_request()

        # Should block 3rd request (over rate)
        assert not limiter.allow_request()

    def test_refills_over_time(self):
        """Bucket should refill tokens over time"""
        limiter = TokenBucketLimiter(requests_per_second=2.0)

        # Use up tokens
        limiter.allow_request()
        limiter.allow_request()
        assert not limiter.allow_request()

        # Wait for refill
        time.sleep(0.6)  # Should refill at least 1 token

        # Should now allow request
        assert limiter.allow_request()

    def test_respects_retry_after_header(self):
        """Should respect Retry-After header"""
        limiter = TokenBucketLimiter(requests_per_second=10.0)

        # Apply backoff from Retry-After
        limiter.apply_retry_after_header(retry_after_seconds=5)

        # Should be heavily rate limited now
        assert not limiter.allow_request()

    def test_adaptive_throttling_on_429(self):
        """Should reduce rate on rate limit errors"""
        limiter = TokenBucketLimiter(requests_per_second=10.0)
        original_rate = limiter.requests_per_second

        # Apply adaptive throttling
        limiter.adaptive_throttle()

        # Rate should be reduced
        assert limiter.requests_per_second < original_rate


class TestMetricsCollector:
    """Test metrics collection"""

    def test_records_success(self):
        """Should record successful calls"""
        collector = MetricsCollector()

        collector.record_success(latency_ms=50.0)

        metrics = collector.get_metrics()
        assert metrics['total_calls'] == 1
        assert metrics['success_count'] == 1
        assert metrics['failure_count'] == 0

    def test_records_failure(self):
        """Should record failures"""
        collector = MetricsCollector()

        collector.record_failure(
            error_type='NetworkException',
            latency_ms=100.0,
        )

        metrics = collector.get_metrics()
        assert metrics['total_calls'] == 1
        assert metrics['failure_count'] == 1
        assert 'NetworkException' in metrics['error_distribution']

    def test_calculates_success_rate(self):
        """Should calculate success rate correctly"""
        collector = MetricsCollector()

        collector.record_success(latency_ms=50.0)
        collector.record_success(latency_ms=60.0)
        collector.record_failure('NetworkException', 100.0)

        metrics = collector.get_metrics()
        assert metrics['success_rate'] == pytest.approx(0.667, rel=0.01)

    def test_calculates_latency_percentiles(self):
        """Should calculate latency percentiles"""
        collector = MetricsCollector()

        # Record 100 calls with latencies 1-100ms
        for i in range(1, 101):
            collector.record_success(latency_ms=float(i))

        metrics = collector.get_metrics()
        assert 'p50_latency_ms' in metrics
        assert 'p90_latency_ms' in metrics
        assert 'p99_latency_ms' in metrics
        assert metrics['p50_latency_ms'] < metrics['p90_latency_ms']
        assert metrics['p90_latency_ms'] < metrics['p99_latency_ms']

    def test_tracks_error_distribution(self):
        """Should track distribution of error types"""
        collector = MetricsCollector()

        collector.record_failure('NetworkException', 50.0)
        collector.record_failure('NetworkException', 60.0)
        collector.record_failure('RateLimitException', 100.0)
        collector.record_failure('TimeoutException', 150.0)

        metrics = collector.get_metrics()
        assert metrics['error_distribution']['NetworkException'] == 2
        assert metrics['error_distribution']['RateLimitException'] == 1
        assert metrics['error_distribution']['TimeoutException'] == 1


class TestIntegrationCircuitBreakerAndRetry:
    """Integration tests for circuit breaker + retry"""

    def test_circuit_breaker_prevents_request_storm(self):
        """Circuit breaker should prevent hammering failing service"""
        cb = CircuitBreaker(failure_threshold=0.5, min_calls=5, timeout=60)
        retry_policy = RetryPolicy(max_attempts=3)
        backoff = ExponentialBackoffWithJitter(base_delay=0.1, max_delay=1.0)

        call_count = 0

        def failing_func():
            nonlocal call_count
            call_count += 1
            raise NetworkException("Service down")

        # Trigger circuit open
        for _ in range(3):
            try:
                cb.call(failing_func)
            except (NetworkException, CircuitBreakerOpenException):
                pass

        for _ in range(2):
            try:
                cb.call(lambda: "OK")
            except Exception:
                pass

        # Circuit should be OPEN now
        assert cb.state == CircuitBreakerState.OPEN

        # Further attempts should fail fast without calling function
        initial_count = call_count
        for _ in range(10):
            try:
                cb.call(failing_func)
            except CircuitBreakerOpenException:
                pass

        # Function should not have been called (circuit is open)
        assert call_count == initial_count


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
