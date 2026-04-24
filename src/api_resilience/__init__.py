"""
API Resilience Module

Provides robust error handling, retry logic, circuit breaking, and rate limiting
for API clients. Uses a decorator pattern to wrap existing clients with zero
breaking changes.

Usage:
    from src.api_resilience import ResilientAPIClient, load_config

    config = load_config('config/api_resilience.yaml')
    resilient_client = ResilientAPIClient(
        original_client,
        config=config['kalshi']
    )

    # Use as normal - automatic retry, circuit breaker, rate limiting
    markets = resilient_client.get_markets()
"""

from .exceptions import (
    APIException,
    RetriableAPIException,
    RateLimitException,
    NetworkException,
    ServerException,
    NonRetriableAPIException,
    AuthenticationException,
    NotFoundException,
    BadRequestException,
    CircuitBreakerOpenException,
)
from .retry_strategies import (
    RetryStrategy,
    ExponentialBackoffWithJitter,
    RetryPolicy,
)
from .circuit_breaker import (
    CircuitBreakerState,
    CircuitBreaker,
)
from .rate_limiter import RateLimiter
from .decorators import ResilientAPIClient
from .metrics_collector import MetricsCollector

__all__ = [
    # Exceptions
    'APIException',
    'RetriableAPIException',
    'RateLimitException',
    'NetworkException',
    'ServerException',
    'NonRetriableAPIException',
    'AuthenticationException',
    'NotFoundException',
    'BadRequestException',
    'CircuitBreakerOpenException',
    # Retry
    'RetryStrategy',
    'ExponentialBackoffWithJitter',
    'RetryPolicy',
    # Circuit Breaker
    'CircuitBreakerState',
    'CircuitBreaker',
    # Rate Limiting
    'RateLimiter',
    # Decorator
    'ResilientAPIClient',
    # Metrics
    'MetricsCollector',
]
