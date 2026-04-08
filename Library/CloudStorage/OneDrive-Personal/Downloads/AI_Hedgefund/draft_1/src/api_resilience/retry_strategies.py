"""Retry strategies with exponential backoff and jitter"""

import random
import time
from abc import ABC, abstractmethod
from typing import Tuple, Set, Type


class RetryStrategy(ABC):
    """Base class for retry strategies"""
    @abstractmethod
    def get_delay(self, attempt: int) -> float:
        """Calculate delay before next retry"""
        pass


class ExponentialBackoffWithJitter(RetryStrategy):
    """Exponential backoff with full or decorrelated jitter"""

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
        jitter_type: str = "full"
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.jitter_type = jitter_type
        self.last_delay = base_delay

    def get_delay(self, attempt: int) -> float:
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)

        if not self.jitter:
            return delay

        if self.jitter_type == "full":
            return random.uniform(0, delay)
        else:  # decorrelated
            self.last_delay = min(
                random.uniform(self.base_delay, self.last_delay * 3),
                self.max_delay
            )
            return self.last_delay

        return delay


class RetryPolicy:
    """Retry policy with configurable strategy and max attempts"""

    def __init__(
        self,
        max_attempts: int = 3,
        strategy: RetryStrategy = None,
        retriable_exceptions: Tuple[Type[Exception], ...] = None,
        retry_on_status_codes: Set[int] = None
    ):
        self.max_attempts = max_attempts
        self.strategy = strategy or ExponentialBackoffWithJitter()
        self.retriable_exceptions = retriable_exceptions or (Exception,)
        self.retry_on_status_codes = retry_on_status_codes or {429, 500, 502, 503, 504}

    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """Check if we should retry this exception"""
        if attempt >= self.max_attempts:
            return False

        if isinstance(exception, self.retriable_exceptions):
            return True

        if hasattr(exception, 'response') and exception.response:
            status_code = getattr(exception.response, 'status_code', None)
            if status_code in self.retry_on_status_codes:
                return True

        return False

    def get_delay(self, attempt: int) -> float:
        return self.strategy.get_delay(attempt)
