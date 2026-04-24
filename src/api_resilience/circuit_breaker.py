"""Circuit breaker pattern implementation"""

import threading
from collections import deque
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict

import logging

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Circuit breaker with sliding window failure tracking"""

    def __init__(
        self,
        name: str,
        failure_threshold: float = 0.5,
        min_calls: int = 10,
        timeout: float = 60.0,
        half_open_max_calls: int = 3,
        window_size: int = 100
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.min_calls = min_calls
        self.timeout = timeout
        self.half_open_max_calls = half_open_max_calls

        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0

        self.call_results = deque(maxlen=window_size)
        self._lock = threading.RLock()

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection"""
        with self._lock:
            if self.state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to_half_open()
                else:
                    from .exceptions import CircuitBreakerOpenException
                    raise CircuitBreakerOpenException(
                        f"Circuit breaker '{self.name}' is OPEN"
                    )

            if self.state == CircuitBreakerState.HALF_OPEN:
                if self.half_open_calls >= self.half_open_max_calls:
                    from .exceptions import CircuitBreakerOpenException
                    raise CircuitBreakerOpenException(
                        f"Circuit breaker '{self.name}' max half-open calls exceeded"
                    )
                self.half_open_calls += 1

        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure()
            raise

    def _record_success(self):
        with self._lock:
            self.success_count += 1
            self.call_results.append(True)

            if self.state == CircuitBreakerState.HALF_OPEN:
                self._transition_to_closed()

    def _record_failure(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.utcnow()
            self.call_results.append(False)

            if self._should_open():
                self._transition_to_open()

    def _should_open(self) -> bool:
        total_calls = len(self.call_results)
        if total_calls < self.min_calls:
            return False

        failures = sum(1 for r in self.call_results if not r)
        failure_rate = failures / total_calls

        return failure_rate >= self.failure_threshold

    def _should_attempt_reset(self) -> bool:
        if not self.last_failure_time:
            return True

        elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
        return elapsed >= self.timeout

    def _transition_to_open(self):
        logger.warning(f"Circuit breaker '{self.name}' OPEN")
        self.state = CircuitBreakerState.OPEN

    def _transition_to_half_open(self):
        logger.info(f"Circuit breaker '{self.name}' -> HALF_OPEN")
        self.state = CircuitBreakerState.HALF_OPEN
        self.half_open_calls = 0

    def _transition_to_closed(self):
        logger.info(f"Circuit breaker '{self.name}' -> CLOSED (recovered)")
        self.state = CircuitBreakerState.CLOSED
        self.half_open_calls = 0
        self.failure_count = 0

    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state"""
        with self._lock:
            return {
                "name": self.name,
                "state": self.state.value,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "failure_rate": self._get_failure_rate(),
                "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None
            }

    def _get_failure_rate(self) -> float:
        if not self.call_results:
            return 0.0
        failures = sum(1 for r in self.call_results if not r)
        return failures / len(self.call_results)
