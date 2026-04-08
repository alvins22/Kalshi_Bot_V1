"""ResilientAPIClient decorator wrapper"""

import time
import logging
from functools import wraps
from typing import Any, Callable

import requests

from .exceptions import (
    APIException, RetriableAPIException, RateLimitException,
    NetworkException, ServerException, AuthenticationException,
    NotFoundException, BadRequestException, CircuitBreakerOpenException,
    MaxRetriesExceededException
)
from .retry_strategies import RetryPolicy, ExponentialBackoffWithJitter
from .circuit_breaker import CircuitBreaker
from .rate_limiter import RateLimiter
from .metrics_collector import MetricsCollector

logger = logging.getLogger(__name__)


class ResilientAPIClient:
    """Wrapper adding resilience to any API client"""

    def __init__(self, client: Any, config: dict = None, logger_instance: logging.Logger = None):
        self.client = client
        self.config = config or {}
        self.logger = logger_instance or logger

        self.retry_policy = RetryPolicy(**self.config.get('retry', {}))
        self.circuit_breaker = CircuitBreaker(
            name=f"{client.__class__.__name__}",
            **self.config.get('circuit_breaker', {})
        )
        self.rate_limiter = RateLimiter(**self.config.get('rate_limiter', {}))
        self.metrics = MetricsCollector()

    def __getattr__(self, name: str):
        attr = getattr(self.client, name)
        if not callable(attr):
            return attr

        @wraps(attr)
        def resilient_wrapper(*args, **kwargs):
            return self._execute_with_resilience(attr, *args, **kwargs)

        return resilient_wrapper

    def _execute_with_resilience(self, func: Callable, *args, **kwargs) -> Any:
        func_name = func.__name__
        attempt = 0

        while attempt < self.retry_policy.max_attempts:
            try:
                if not self.rate_limiter.acquire():
                    raise RateLimitException("Rate limiter timeout")

                start_time = time.time()

                def execute():
                    result = func(*args, **kwargs)
                    latency = time.time() - start_time
                    self.metrics.record_success(func_name, latency)
                    return result

                return self.circuit_breaker.call(execute)

            except Exception as e:
                attempt += 1
                classified_error = self._classify_exception(e)
                self.metrics.record_failure(func_name, type(classified_error).__name__)

                if isinstance(classified_error, RateLimitException):
                    if hasattr(e, 'response'):
                        self.rate_limiter.handle_rate_limit_response(e.response)

                if not self.retry_policy.should_retry(classified_error, attempt):
                    raise classified_error

                delay = self.retry_policy.get_delay(attempt)
                self.logger.warning(
                    f"Attempt {attempt} failed for {func_name}, "
                    f"retrying in {delay:.2f}s: {classified_error}"
                )
                time.sleep(delay)

        raise MaxRetriesExceededException(
            f"Max retries ({self.retry_policy.max_attempts}) exceeded for {func_name}"
        )

    def _classify_exception(self, error: Exception) -> APIException:
        if isinstance(error, APIException):
            return error

        if isinstance(error, requests.exceptions.ConnectionError):
            return NetworkException("Connection failed", original_error=error)

        if isinstance(error, requests.exceptions.Timeout):
            return NetworkException("Request timeout", original_error=error)

        if isinstance(error, requests.exceptions.HTTPError):
            status_code = error.response.status_code if error.response else None

            if status_code == 429:
                return RateLimitException("Rate limit exceeded", response=error.response, original_error=error)
            elif status_code in (401, 403):
                return AuthenticationException(f"Auth failed ({status_code})", response=error.response, original_error=error)
            elif status_code == 404:
                return NotFoundException("Not found", response=error.response, original_error=error)
            elif status_code == 400:
                return BadRequestException("Bad request", response=error.response, original_error=error)
            elif status_code in (500, 502, 503, 504):
                return ServerException(f"Server error ({status_code})", response=error.response, original_error=error)

        return RetriableAPIException(f"Unknown error: {str(error)}", original_error=error)

    def get_health_status(self) -> dict:
        """Get comprehensive health status"""
        return {
            "client": self.client.__class__.__name__,
            "circuit_breaker": self.circuit_breaker.get_state(),
            "metrics": self.metrics.get_summary(),
            "rate_limited": self.rate_limiter.rate_limited_until is not None
        }
