"""Metrics collection for API calls"""

import statistics
import threading
from collections import deque, Counter
from typing import Dict, Any

import logging

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects metrics on API calls"""

    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.success_count = 0
        self.failure_count = 0
        self.latencies = deque(maxlen=window_size)
        self.error_types = Counter()
        self._lock = threading.Lock()

    def record_success(self, endpoint: str, latency: float):
        with self._lock:
            self.success_count += 1
            self.latencies.append(latency)

    def record_failure(self, endpoint: str, error_type: str):
        with self._lock:
            self.failure_count += 1
            self.error_types[error_type] += 1

    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary"""
        with self._lock:
            total = self.success_count + self.failure_count

            return {
                "total_calls": total,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "success_rate": self.success_count / total if total > 0 else 0.0,
                "latency_p50": self._percentile(50),
                "latency_p90": self._percentile(90),
                "latency_p95": self._percentile(95),
                "latency_p99": self._percentile(99),
                "error_types": dict(self.error_types.most_common(10)),
            }

    def _percentile(self, p: int) -> float:
        if not self.latencies:
            return 0.0
        try:
            return statistics.quantiles(list(self.latencies), n=100)[p - 1]
        except:
            return 0.0
