"""Rate limiter with token bucket algorithm"""

import threading
import time
from datetime import datetime, timedelta
from typing import Optional

import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter with adaptive throttling"""

    def __init__(
        self,
        requests_per_second: float = 10.0,
        burst_size: int = 20,
        adaptive: bool = True
    ):
        self.requests_per_second = requests_per_second
        self.burst_size = burst_size
        self.adaptive = adaptive

        self.tokens = burst_size
        self.last_update = time.time()
        self.rate_limited_until: Optional[datetime] = None

        self._lock = threading.Lock()

    def acquire(self, timeout: float = 10.0) -> bool:
        """Acquire token to make request"""
        start_time = time.time()

        while True:
            with self._lock:
                if self.rate_limited_until:
                    if datetime.utcnow() < self.rate_limited_until:
                        wait_time = (self.rate_limited_until - datetime.utcnow()).total_seconds()
                        logger.debug(f"Rate limited, waiting {wait_time:.1f}s")
                    else:
                        self.rate_limited_until = None

                # Refill tokens
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(
                    self.burst_size,
                    self.tokens + elapsed * self.requests_per_second
                )
                self.last_update = now

                # Try to acquire
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return True

            if time.time() - start_time > timeout:
                return False

            time.sleep(0.1)

    def handle_rate_limit_response(self, response):
        """Handle 429 response and extract retry-after"""
        with self._lock:
            retry_after = None

            if hasattr(response, 'headers'):
                retry_after_header = response.headers.get('Retry-After')
                if retry_after_header:
                    try:
                        retry_after = int(retry_after_header)
                    except ValueError:
                        pass

                reset_header = response.headers.get('X-RateLimit-Reset')
                if reset_header and not retry_after:
                    reset_timestamp = int(reset_header)
                    retry_after = reset_timestamp - time.time()

            if retry_after is None:
                retry_after = 60

            self.rate_limited_until = datetime.utcnow() + timedelta(seconds=retry_after)

            if self.adaptive:
                self.requests_per_second *= 0.8
                logger.info(f"Adaptively reduced rate to {self.requests_per_second:.2f} req/s")

            logger.warning(f"Rate limited, backing off for {retry_after:.1f}s")
