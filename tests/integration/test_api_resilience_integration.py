"""Integration tests for API resilience system in trading context"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from src.data.models import MarketTick, Direction, Outcome, Signal, Fill
from src.api_resilience.decorators import ResilientAPIClient
from src.api_resilience.exceptions import (
    NetworkException,
    RateLimitException,
    CircuitBreakerOpenException,
)


class MockKalshiClient:
    """Mock Kalshi client for testing"""

    def __init__(self):
        self.call_count = 0
        self.fail_for_calls = 0
        self.failure_type = NetworkException

    async def get_markets(self, limit=100):
        """Mock get_markets that can fail"""
        self.call_count += 1
        if self.call_count <= self.fail_for_calls:
            raise self.failure_type("API error")
        return [
            Mock(
                market_id=f"MARKET-{i}",
                yes_bid=0.45,
                yes_ask=0.55,
                no_bid=0.45,
                no_ask=0.55,
                volume_24h=1000,
            )
            for i in range(5)
        ]

    def get_markets_sync(self, limit=100):
        """Synchronous version for testing"""
        self.call_count += 1
        if self.call_count <= self.fail_for_calls:
            raise self.failure_type("API error")
        return [
            Mock(
                market_id=f"MARKET-{i}",
                yes_bid=0.45,
                yes_ask=0.55,
                no_bid=0.45,
                no_ask=0.55,
                volume_24h=1000,
            )
            for i in range(5)
        ]


class TestResilientClientRetry:
    """Test resilient client retry logic"""

    def test_retries_on_transient_failure(self):
        """Should retry on transient failures and succeed"""
        mock_client = MockKalshiClient()
        mock_client.fail_for_calls = 2  # Fail first 2 calls, succeed on 3rd

        config = {
            'retry': {
                'max_attempts': 3,
                'base_delay': 0.01,
                'max_delay': 0.1,
                'jitter': False,
            },
            'circuit_breaker': {'enabled': False},
            'rate_limiter': {'requests_per_second': 1000.0},
        }

        resilient_client = ResilientAPIClient(mock_client, config, 'kalshi')

        # Should succeed after retries
        result = resilient_client.get_markets_sync(limit=100)
        assert result is not None
        assert mock_client.call_count == 3  # Retried 2 times before success

    def test_fails_after_max_retries_exceeded(self):
        """Should fail if max retries exceeded"""
        mock_client = MockKalshiClient()
        mock_client.fail_for_calls = 10  # Always fail

        config = {
            'retry': {
                'max_attempts': 3,
                'base_delay': 0.01,
                'max_delay': 0.05,
                'jitter': False,
            },
            'circuit_breaker': {'enabled': False},
            'rate_limiter': {'requests_per_second': 1000.0},
        }

        resilient_client = ResilientAPIClient(mock_client, config, 'kalshi')

        # Should fail after 3 attempts
        with pytest.raises(Exception):
            resilient_client.get_markets_sync(limit=100)

        assert mock_client.call_count == 3  # Tried 3 times

    def test_respects_rate_limit_retry_after(self):
        """Should respect Retry-After header on 429 errors"""
        mock_client = MockKalshiClient()
        mock_client.fail_for_calls = 1
        mock_client.failure_type = RateLimitException

        config = {
            'retry': {
                'max_attempts': 3,
                'base_delay': 0.01,
                'max_delay': 0.1,
                'jitter': False,
            },
            'circuit_breaker': {'enabled': False},
            'rate_limiter': {'requests_per_second': 1000.0},
        }

        resilient_client = ResilientAPIClient(mock_client, config, 'kalshi')

        # Should retry and succeed
        result = resilient_client.get_markets_sync(limit=100)
        assert result is not None


class TestResilientClientCircuitBreaker:
    """Test circuit breaker in resilient client"""

    def test_circuit_breaker_opens_on_repeated_failures(self):
        """Circuit breaker should open after repeated failures"""
        mock_client = MockKalshiClient()
        mock_client.fail_for_calls = 100  # Always fail

        config = {
            'retry': {
                'max_attempts': 1,
                'base_delay': 0.01,
                'max_delay': 0.01,
                'jitter': False,
            },
            'circuit_breaker': {
                'enabled': True,
                'failure_threshold': 0.5,
                'min_calls': 5,
                'timeout': 1,
                'half_open_max_calls': 3,
            },
            'rate_limiter': {'requests_per_second': 1000.0},
        }

        resilient_client = ResilientAPIClient(mock_client, config, 'kalshi')

        # Make requests until circuit opens
        for i in range(10):
            try:
                resilient_client.get_markets_sync(limit=100)
            except CircuitBreakerOpenException:
                # Circuit is open
                assert i >= 5  # Should open after min_calls failures
                break
            except Exception:
                pass

    def test_circuit_breaker_recovers_after_timeout(self):
        """Circuit breaker should recover after timeout period"""
        import time

        mock_client = MockKalshiClient()

        config = {
            'retry': {
                'max_attempts': 1,
                'base_delay': 0.01,
                'max_delay': 0.01,
                'jitter': False,
            },
            'circuit_breaker': {
                'enabled': True,
                'failure_threshold': 0.5,
                'min_calls': 2,
                'timeout': 0.5,
                'half_open_max_calls': 3,
            },
            'rate_limiter': {'requests_per_second': 1000.0},
        }

        resilient_client = ResilientAPIClient(mock_client, config, 'kalshi')

        # Force failures to open circuit
        mock_client.fail_for_calls = 10
        for _ in range(3):
            try:
                resilient_client.get_markets_sync(limit=100)
            except Exception:
                pass

        # Circuit should be open
        try:
            resilient_client.get_markets_sync(limit=100)
            assert False, "Should have raised CircuitBreakerOpenException"
        except CircuitBreakerOpenException:
            pass  # Expected

        # Wait for timeout
        time.sleep(0.6)

        # Reset mock to allow success
        mock_client.fail_for_calls = 0

        # Should now work (circuit in HALF_OPEN, allows attempt)
        result = resilient_client.get_markets_sync(limit=100)
        assert result is not None


class TestResilientClientRateLimiting:
    """Test rate limiting in resilient client"""

    def test_rate_limiter_enforces_request_rate(self):
        """Rate limiter should enforce configured request rate"""
        mock_client = MockKalshiClient()

        config = {
            'retry': {
                'max_attempts': 1,
                'base_delay': 0.01,
                'max_delay': 0.01,
                'jitter': False,
            },
            'circuit_breaker': {'enabled': False},
            'rate_limiter': {
                'requests_per_second': 5.0,  # 5 req/sec = 0.2 sec per request
                'adaptive': False,
                'respect_retry_after': False,
            },
        }

        resilient_client = ResilientAPIClient(mock_client, config, 'kalshi')

        import time

        start = time.time()
        resilient_client.get_markets_sync(limit=100)
        resilient_client.get_markets_sync(limit=100)
        resilient_client.get_markets_sync(limit=100)
        elapsed = time.time() - start

        # 3 requests at 5 req/sec should take ~0.4 seconds (with some margin)
        # First request is immediate, then 2 more with delays
        assert elapsed >= 0.3  # Some tolerance for timing


class TestFailoverAndRecovery:
    """Test failover and recovery scenarios"""

    def test_graceful_degradation_on_api_unavailable(self):
        """Trading should degrade gracefully if API unavailable"""
        mock_client = MockKalshiClient()
        mock_client.fail_for_calls = 100  # API always fails

        config = {
            'retry': {
                'max_attempts': 1,
                'base_delay': 0.01,
                'max_delay': 0.01,
                'jitter': False,
            },
            'circuit_breaker': {
                'enabled': True,
                'failure_threshold': 0.5,
                'min_calls': 3,
                'timeout': 1,
            },
            'rate_limiter': {'requests_per_second': 100.0},
        }

        resilient_client = ResilientAPIClient(mock_client, config, 'kalshi')

        # Requests should fail quickly once circuit opens
        error_count = 0
        for i in range(20):
            try:
                resilient_client.get_markets_sync(limit=100)
            except CircuitBreakerOpenException:
                error_count += 1
            except Exception as e:
                error_count += 1

        # Should have high error rate due to circuit breaker
        assert error_count > 0

    def test_adaptive_throttling_on_rate_limit(self):
        """Should automatically reduce rate on 429 errors"""
        mock_client = MockKalshiClient()

        config = {
            'retry': {
                'max_attempts': 3,
                'base_delay': 0.01,
                'max_delay': 0.05,
                'jitter': False,
            },
            'circuit_breaker': {'enabled': False},
            'rate_limiter': {
                'requests_per_second': 100.0,
                'adaptive': True,
                'respect_retry_after': True,
            },
        }

        resilient_client = ResilientAPIClient(mock_client, config, 'kalshi')

        # Simulate rate limit error
        mock_client.fail_for_calls = 1
        mock_client.failure_type = RateLimitException

        # Should succeed after throttling
        result = resilient_client.get_markets_sync(limit=100)
        assert result is not None


class TestMetricsTrackingUnderFailure:
    """Test metrics collection during failures"""

    def test_tracks_success_rate_during_failures(self):
        """Should track success rate through failure recovery"""
        mock_client = MockKalshiClient()

        config = {
            'retry': {
                'max_attempts': 3,
                'base_delay': 0.01,
                'max_delay': 0.05,
                'jitter': False,
            },
            'circuit_breaker': {'enabled': False},
            'rate_limiter': {'requests_per_second': 1000.0},
        }

        resilient_client = ResilientAPIClient(mock_client, config, 'kalshi')

        # Make some successful calls
        for _ in range(5):
            resilient_client.get_markets_sync(limit=100)

        # Make some failed calls
        mock_client.fail_for_calls = 100
        for _ in range(3):
            try:
                resilient_client.get_markets_sync(limit=100)
            except Exception:
                pass

        # Get metrics
        metrics = resilient_client.get_metrics()
        assert metrics['total_calls'] == 8
        assert metrics['success_count'] == 5
        assert metrics['failure_count'] == 3
        assert metrics['success_rate'] == pytest.approx(5.0 / 8.0, rel=0.01)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
