"""Dynamic Conditional Correlation (DCC) matrix"""
import numpy as np
import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class DynamicConditionalCorrelation:
    """DCC model for adaptive correlation estimation"""

    def __init__(self, alpha: float = 0.05, beta: float = 0.94, lookback: int = 60):
        self.alpha = alpha
        self.beta = beta
        self.lookback = lookback
        self.returns_history: Dict[str, list] = {}
        self.correlation_matrix = None
        self.std_dev: Dict[str, float] = {}

    def add_returns(self, returns_dict: Dict[str, float]):
        """Add return observations for multiple markets"""
        for market_id, ret in returns_dict.items():
            if market_id not in self.returns_history:
                self.returns_history[market_id] = []
            self.returns_history[market_id].append(ret)
            if len(self.returns_history[market_id]) > self.lookback * 2:
                self.returns_history[market_id] = self.returns_history[market_id][-self.lookback * 2:]

    def update_dcc(self):
        """Update DCC correlation matrix"""
        if len(self.returns_history) < 2:
            return

        market_ids = list(self.returns_history.keys())
        n = len(market_ids)

        # Calculate standard deviations
        for mid in market_ids:
            rets = np.array(self.returns_history[mid][-self.lookback:])
            if len(rets) > 1:
                self.std_dev[mid] = max(np.std(rets), 1e-6)

        # Standardized returns
        Z = []
        for mid in market_ids:
            rets = np.array(self.returns_history[mid][-self.lookback:])
            std = self.std_dev.get(mid, 1e-6)
            z = rets / std
            Z.append(z)

        Z = np.array(Z)

        # Unconditional correlation
        if self.correlation_matrix is None:
            self.correlation_matrix = np.corrcoef(Z)
        else:
            # DCC update: Q_t = (1-a-b)*Q_bar + a*z*z' + b*Q_{t-1}
            z_t = Z[:, -1:].T  # Last observation
            Q_update = (1 - self.alpha - self.beta) * np.corrcoef(Z)
            Q_update += self.alpha * (z_t.T @ z_t)
            Q_update += self.beta * self.correlation_matrix

            # Normalize to correlation
            diag = np.sqrt(np.diag(Q_update))
            self.correlation_matrix = Q_update / (diag[:, None] * diag[None, :])

    def get_correlation(self, market_i: str, market_j: str) -> float:
        """Get current correlation between two markets"""
        if self.correlation_matrix is None:
            return 0.0

        market_ids = list(self.returns_history.keys())
        if market_i not in market_ids or market_j not in market_ids:
            return 0.0

        i = market_ids.index(market_i)
        j = market_ids.index(market_j)

        return float(np.clip(self.correlation_matrix[i, j], -1.0, 1.0))

    def get_correlation_stress_score(self) -> float:
        """Score 0-1: high = correlations breaking down"""
        if self.correlation_matrix is None or len(self.returns_history) < 2:
            return 0.5

        # Calculate average absolute correlation
        corr_abs = np.abs(np.triu(self.correlation_matrix, k=1))
        if corr_abs.size == 0:
            return 0.5

        avg_corr = np.nanmean(corr_abs)
        # Higher average correlation = higher stress (convergence to 1)
        stress = min(1.0, max(0.0, avg_corr))

        return float(stress)
