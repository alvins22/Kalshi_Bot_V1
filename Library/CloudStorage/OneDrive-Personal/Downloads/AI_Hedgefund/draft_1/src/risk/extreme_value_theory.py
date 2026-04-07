"""Extreme Value Theory for tail risk modeling"""
import numpy as np
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ExtremeValueTheory:
    """EVT-based Value at Risk estimation"""

    def __init__(self, threshold_pct: float = 90, fit_window: int = 250):
        self.threshold_pct = threshold_pct
        self.fit_window = fit_window
        self.market_var: Dict[str, float] = {}
        self.market_returns: Dict[str, list] = {}

    def add_return(self, market_id: str, ret: float):
        """Add return observation"""
        if market_id not in self.market_returns:
            self.market_returns[market_id] = []
        self.market_returns[market_id].append(ret)
        if len(self.market_returns[market_id]) > self.fit_window * 2:
            self.market_returns[market_id] = self.market_returns[market_id][-self.fit_window * 2:]

    def fit_pareto(self, market_id: str):
        """Fit Pareto distribution to tail"""
        if market_id not in self.market_returns or len(self.market_returns[market_id]) < 10:
            return

        returns = np.array(self.market_returns[market_id])
        threshold = np.percentile(returns, self.threshold_pct)
        tail = returns[returns > threshold]

        if len(tail) < 3:
            return

        # Pareto shape parameter: alpha = n / sum(ln(x_i / u))
        alpha = len(tail) / np.sum(np.log(tail / threshold) + 1e-10)
        alpha = max(0.5, min(alpha, 10.0))

        self.market_var[market_id] = alpha

    def get_var(self, market_id: str, confidence: float = 0.95) -> float:
        """Get Value at Risk"""
        if market_id not in self.market_returns or len(self.market_returns[market_id]) < 10:
            return 0.05

        self.fit_pareto(market_id)

        returns = np.array(self.market_returns[market_id])
        threshold = np.percentile(returns, self.threshold_pct)

        # EVT VaR: u + (beta/alpha) * ((1-p)/(1-F_u))^(-1/alpha) - 1
        alpha = self.market_var.get(market_id, 1.5)
        quantile = (1 - confidence) / (1 - self.threshold_pct / 100)

        if quantile > 0:
            var = threshold + (threshold / alpha) * (quantile ** (-1 / alpha) - 1)
        else:
            var = threshold

        return float(np.clip(var, -1.0, 1.0))

    def get_tail_risk_score(self, market_id: str) -> float:
        """Score 0-1 indicating tail risk (0=low, 1=high)"""
        if market_id not in self.market_returns:
            return 0.5

        var_95 = self.get_var(market_id, 0.95)
        var_99 = self.get_var(market_id, 0.99)
        tail_ratio = abs(var_99 / max(abs(var_95), 1e-6))

        return float(np.clip(tail_ratio / 2.0, 0.0, 1.0))
