"""Custom exception hierarchy for API error handling"""

from datetime import datetime
from typing import Optional


class APIException(Exception):
    """Base exception for all API errors"""
    def __init__(self, message: str, response=None, original_error=None):
        super().__init__(message)
        self.response = response
        self.original_error = original_error
        self.timestamp = datetime.utcnow()


class RetriableAPIException(APIException):
    """Errors that can be retried (network, transient server errors)"""
    pass


class RateLimitException(RetriableAPIException):
    """Rate limit exceeded (HTTP 429)"""
    def __init__(self, retry_after: Optional[int] = None, **kwargs):
        super().__init__(**kwargs)
        self.retry_after = retry_after


class NetworkException(RetriableAPIException):
    """Network connectivity issues"""
    pass


class ServerException(RetriableAPIException):
    """Server errors (500, 502, 503, 504)"""
    pass


class NonRetriableAPIException(APIException):
    """Errors that should NOT be retried"""
    pass


class AuthenticationException(NonRetriableAPIException):
    """Authentication failed (401, 403)"""
    pass


class NotFoundException(NonRetriableAPIException):
    """Resource not found (404)"""
    pass


class BadRequestException(NonRetriableAPIException):
    """Invalid request (400)"""
    pass


class CircuitBreakerOpenException(APIException):
    """Circuit breaker is open, blocking requests"""
    pass


class MaxRetriesExceededException(APIException):
    """Max retries exceeded"""
    pass
