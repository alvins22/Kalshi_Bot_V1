"""Resilient Kalshi client with exponential backoff, circuit breaker, and rate limiting"""

import logging
from typing import Any, Dict
import yaml

from src.api_resilience.decorators import ResilientAPIClient
from src.exchanges.kalshi.kalshi_client import KalshiClient

logger = logging.getLogger(__name__)


class ResilientKalshiClient:
    """Drop-in replacement for KalshiClient with resilience features

    Wraps the standard KalshiClient with:
    - Exponential backoff with jitter for transient failures
    - Circuit breaker to prevent cascading failures
    - Rate limiting with adaptive throttling
    - Comprehensive metrics collection
    """

    def __init__(
        self,
        api_key: str,
        private_key_path: str,
        is_demo: bool = True,
        timeout: int = 10,
        resilience_config_path: str = None,
    ):
        """Initialize resilient Kalshi client

        Args:
            api_key: Kalshi API key
            private_key_path: Path to RSA private key PEM file
            is_demo: Use demo environment
            timeout: Request timeout in seconds
            resilience_config_path: Path to api_resilience.yaml config file
        """
        # Create base Kalshi client
        self.base_client = KalshiClient(
            api_key=api_key,
            private_key_path=private_key_path,
            is_demo=is_demo,
            timeout=timeout,
        )

        # Load resilience configuration
        resilience_config = self._load_resilience_config(resilience_config_path)
        kalshi_config = resilience_config.get('kalshi', {})

        # Wrap with resilience decorator
        self._resilient_client = ResilientAPIClient(
            client=self.base_client,
            config=kalshi_config,
            exchange_name='kalshi'
        )

        logger.info(
            f"Initialized ResilientKalshiClient with circuit breaker, "
            f"retry, and rate limiting"
        )

    def _load_resilience_config(self, config_path: str = None) -> Dict[str, Any]:
        """Load resilience configuration from YAML file

        Args:
            config_path: Path to config file. If None, uses default location.

        Returns:
            Resilience configuration dictionary
        """
        if config_path is None:
            config_path = "config/api_resilience.yaml"

        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded resilience config from {config_path}")
            return config
        except FileNotFoundError:
            logger.warning(
                f"Resilience config not found at {config_path}, "
                f"using defaults"
            )
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default resilience configuration"""
        return {
            'kalshi': {
                'retry': {
                    'max_attempts': 3,
                    'base_delay': 1.0,
                    'max_delay': 60.0,
                    'jitter': True,
                },
                'circuit_breaker': {
                    'enabled': True,
                    'failure_threshold': 0.5,
                    'min_calls': 10,
                    'timeout': 60.0,
                    'half_open_max_calls': 3,
                },
                'rate_limiter': {
                    'requests_per_second': 10.0,
                    'adaptive': True,
                    'respect_retry_after': True,
                },
            }
        }

    def __getattr__(self, name: str) -> Any:
        """Transparently delegate all method calls to resilient client

        This allows ResilientKalshiClient to act as a drop-in replacement
        for KalshiClient. All method calls are automatically wrapped with
        resilience features.
        """
        return getattr(self._resilient_client, name)

    def get_metrics(self) -> Dict[str, Any]:
        """Get resilience metrics

        Returns:
            Dictionary with success/failure rates, latency stats, etc.
        """
        return self._resilient_client.get_metrics()

    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get circuit breaker status

        Returns:
            Dictionary with circuit breaker state, failure count, etc.
        """
        metrics = self.get_metrics()
        return {
            'circuit_breaker_state': metrics.get('circuit_breaker_state', 'UNKNOWN'),
            'failure_rate': metrics.get('failure_rate', 0.0),
            'total_calls': metrics.get('total_calls', 0),
            'failure_count': metrics.get('failure_count', 0),
        }
