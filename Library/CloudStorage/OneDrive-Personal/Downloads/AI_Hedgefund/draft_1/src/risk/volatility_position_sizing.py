"""Volatility-based position sizing and risk normalization"""

import numpy as np
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class VolatilityMetrics:
    """Volatility statistics for a market"""
    timestamp: datetime
    market_id: str
    volatility: float  # Standard deviation of returns
    half_life: Optional[float] = None  # Mean reversion half-life in bars
    sharpe_ratio: Optional[float] = None
    max_volatility: float = 0.5  # Maximum observed volatility
    min_volatility: float = 0.01  # Minimum observed volatility


class VolatilityCalculator:
    """Calculate rolling volatility and related metrics"""

    def __init__(self, lookback_window: int = 20):
        """
        Initialize volatility calculator

        Args:
            lookback_window: Number of bars for rolling volatility (default 20)
        """
        self.lookback_window = lookback_window
        self.price_history: Dict[str, list] = {}
        self.volatility_cache: Dict[str, VolatilityMetrics] = {}

    def add_price(self, market_id: str, price: float):
        """Add price observation for market"""
        if market_id not in self.price_history:
            self.price_history[market_id] = []
        self.price_history[market_id].append(price)

        # Keep only recent history
        if len(self.price_history[market_id]) > self.lookback_window * 2:
            self.price_history[market_id] = self.price_history[market_id][-(self.lookback_window * 2):]

    def calculate_volatility(self, market_id: str, timestamp: datetime) -> float:
        """
        Calculate rolling volatility from price history

        Args:
            market_id: Market identifier
            timestamp: Current timestamp

        Returns:
            Annualized volatility (assuming prediction markets)
        """
        if market_id not in self.price_history or len(self.price_history[market_id]) < 2:
            return 0.05  # Default to 5% if no history

        prices = np.array(self.price_history[market_id][-self.lookback_window:])

        if len(prices) < 2:
            return 0.05

        # Calculate log returns
        returns = np.diff(np.log(prices))

        if len(returns) == 0:
            return 0.05

        # Rolling standard deviation (annualized for prediction markets)
        volatility = np.std(returns)

        # Bound volatility
        volatility = max(0.01, min(0.5, volatility))

        # Cache result
        self.volatility_cache[market_id] = VolatilityMetrics(
            timestamp=timestamp,
            market_id=market_id,
            volatility=volatility
        )

        return volatility

    def calculate_half_life(self, market_id: str) -> Optional[float]:
        """
        Calculate half-life of mean reversion

        Uses AR(1) model: price(t) = lambda * price(t-1) + noise
        Half-life = -log(2) / log(lambda)

        Args:
            market_id: Market identifier

        Returns:
            Half-life in bars, or None if insufficient data
        """
        if market_id not in self.price_history or len(self.price_history[market_id]) < 10:
            return None

        prices = np.array(self.price_history[market_id][-50:])

        if len(prices) < 10:
            return None

        # Fit AR(1) model: price(t) - mean = lambda * (price(t-1) - mean)
        centered_prices = prices - np.mean(prices)
        x = centered_prices[:-1].reshape(-1, 1)
        y = centered_prices[1:]

        # Linear regression to get lambda
        try:
            lambda_coef = np.linalg.lstsq(x, y, rcond=None)[0][0]
            lambda_coef = float(lambda_coef)

            if lambda_coef <= 0 or lambda_coef >= 1:
                return None

            # Half-life calculation
            half_life = -np.log(2) / np.log(lambda_coef)
            return max(1, half_life)  # At least 1 bar
        except Exception as e:
            logger.debug(f"Half-life calculation error for {market_id}: {e}")
            return None


class VolatilityAdjustedPositionSizer:
    """Position sizing adjusted for volatility and risk parity"""

    def __init__(
        self,
        target_risk_pct: float = 0.02,
        reference_volatility: float = 0.1,
        kelly_fraction: float = 0.25,
        risk_parity: bool = True
    ):
        """
        Initialize volatility-adjusted position sizer

        Args:
            target_risk_pct: Target portfolio risk per trade (default 2%)
            reference_volatility: Reference volatility for scaling (default 10%)
            kelly_fraction: Kelly Criterion fraction for safety (default 0.25)
            risk_parity: Use risk parity weighting across positions (default True)
        """
        self.target_risk_pct = target_risk_pct
        self.reference_volatility = reference_volatility
        self.kelly_fraction = kelly_fraction
        self.risk_parity = risk_parity
        self.volatility_calc = VolatilityCalculator()
        self.market_volatilities: Dict[str, float] = {}

    def update_volatility(self, market_id: str, price: float):
        """Update volatility estimate for market"""
        self.volatility_calc.add_price(market_id, price)

    def calculate_position_size(
        self,
        market_id: str,
        confidence: float,
        available_capital: float,
        current_volatility: Optional[float] = None,
        timestamp: datetime = None
    ) -> float:
        """
        Calculate volatility-adjusted position size

        Formula:
            base_size = target_risk * capital / (volatility * price_move)
            adjusted_size = base_size * min(kelly_fraction, 1.0)
            final_size = adjusted_size * sqrt(reference_vol / current_vol)

        Args:
            market_id: Market identifier
            confidence: Signal confidence (0.0-1.0)
            available_capital: Available capital for this trade
            current_volatility: Current market volatility (optional)
            timestamp: Current timestamp

        Returns:
            Position size as percentage of available capital (0.0-1.0)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        # Get or calculate volatility
        if current_volatility is None:
            current_volatility = self.volatility_calc.calculate_volatility(market_id, timestamp)
        else:
            self.volatility_calc.volatility_cache[market_id] = VolatilityMetrics(
                timestamp=timestamp,
                market_id=market_id,
                volatility=current_volatility
            )

        self.market_volatilities[market_id] = current_volatility

        # Base position size: target_risk / volatility
        # Higher volatility = smaller position
        base_size = self.target_risk_pct / (current_volatility + 1e-6)

        # Scale by confidence (higher confidence = larger position)
        confidence_adjusted = base_size * confidence

        # Apply Kelly fraction for safety
        kelly_adjusted = confidence_adjusted * self.kelly_fraction

        # Volatility normalization: increase size in low-vol, decrease in high-vol
        volatility_ratio = self.reference_volatility / (current_volatility + 1e-6)
        volatility_normalized = kelly_adjusted * np.sqrt(volatility_ratio)

        # Bound between 0 and 1
        final_size = np.clip(volatility_normalized, 0.0, 1.0)

        return final_size

    def calculate_risk_parity_weights(
        self,
        market_ids: list,
        volatilities: Optional[Dict[str, float]] = None
    ) -> Dict[str, float]:
        """
        Calculate risk parity weights for portfolio

        Inverse volatility weighting: weight_i = (1/vol_i) / sum(1/vol_j)

        Args:
            market_ids: List of market IDs
            volatilities: Optional volatility dict (uses cache if None)

        Returns:
            Dictionary of market_id -> weight (sums to 1.0)
        """
        if volatilities is None:
            volatilities = self.market_volatilities

        weights = {}
        inverse_vols = {}

        # Calculate inverse volatilities
        for mid in market_ids:
            vol = volatilities.get(mid, self.reference_volatility)
            vol = max(vol, 0.01)  # Avoid division by zero
            inverse_vols[mid] = 1.0 / vol

        # Normalize to sum to 1.0
        total_inverse_vol = sum(inverse_vols.values())

        if total_inverse_vol > 0:
            weights = {mid: inv_vol / total_inverse_vol for mid, inv_vol in inverse_vols.items()}
        else:
            # Equal weight fallback
            equal_weight = 1.0 / len(market_ids)
            weights = {mid: equal_weight for mid in market_ids}

        return weights

    def calculate_sharpe_adjusted_size(
        self,
        market_id: str,
        expected_return: float,
        volatility: float,
        risk_free_rate: float = 0.02,
        capital: float = 100000
    ) -> float:
        """
        Calculate position size to maximize Sharpe ratio

        Allocate more to strategies with higher Sharpe ratios

        Args:
            market_id: Market identifier
            expected_return: Expected return from strategy
            volatility: Strategy volatility
            risk_free_rate: Risk-free rate (default 2%)
            capital: Available capital

        Returns:
            Recommended position size
        """
        if volatility <= 0:
            return 0.0

        # Sharpe ratio = (return - rf) / volatility
        sharpe = (expected_return - risk_free_rate) / volatility

        # Position size scales with Sharpe ratio
        # Bound between 0 and 1
        position_size = np.tanh(sharpe)  # Smooth bound to [0, 1]
        position_size = np.clip(position_size, 0.0, 1.0)

        return position_size

    def get_volatility_metrics(self, market_id: str) -> Optional[VolatilityMetrics]:
        """Get cached volatility metrics for market"""
        return self.volatility_calc.volatility_cache.get(market_id)

    def get_all_volatilities(self) -> Dict[str, float]:
        """Get all cached volatility measurements"""
        return self.market_volatilities.copy()


class DynamicRiskLimits:
    """Dynamic risk limits that adjust based on volatility and drawdown"""

    def __init__(
        self,
        base_max_position_pct: float = 0.05,
        base_max_daily_loss_pct: float = 0.02,
        base_max_drawdown_pct: float = 0.10
    ):
        """
        Initialize dynamic risk limits

        Args:
            base_max_position_pct: Base max position as % of portfolio
            base_max_daily_loss_pct: Base max daily loss as % of capital
            base_max_drawdown_pct: Base max drawdown as % of peak
        """
        self.base_max_position_pct = base_max_position_pct
        self.base_max_daily_loss_pct = base_max_daily_loss_pct
        self.base_max_drawdown_pct = base_max_drawdown_pct

        self.current_drawdown = 0.0
        self.peak_portfolio_value = 100000.0
        self.daily_pnl = 0.0
        self.volatility_adjustment = 1.0

    def update_drawdown(self, current_value: float, peak_value: float):
        """Update current drawdown"""
        if peak_value > 0:
            self.current_drawdown = (peak_value - current_value) / peak_value
            self.peak_portfolio_value = max(self.peak_portfolio_value, peak_value)

    def update_daily_pnl(self, daily_loss: float):
        """Update daily P&L"""
        self.daily_pnl = daily_loss

    def set_volatility_adjustment(self, volatility: float, reference_vol: float = 0.1):
        """
        Adjust risk limits based on market volatility

        Higher volatility = stricter limits
        """
        self.volatility_adjustment = reference_vol / max(volatility, 0.01)

    def get_max_position_size(self) -> float:
        """Get dynamic max position size"""
        # Reduce limits as drawdown increases
        drawdown_factor = 1.0 - self.current_drawdown
        return self.base_max_position_pct * drawdown_factor * self.volatility_adjustment

    def get_max_daily_loss(self) -> float:
        """Get dynamic max daily loss"""
        drawdown_factor = 1.0 - self.current_drawdown
        return self.base_max_daily_loss_pct * drawdown_factor * self.volatility_adjustment

    def get_max_drawdown(self) -> float:
        """Get max allowed drawdown"""
        return self.base_max_drawdown_pct

    def is_position_allowed(self, position_size: float, current_pct_of_portfolio: float) -> bool:
        """Check if position size is allowed by risk limits"""
        return current_pct_of_portfolio < self.get_max_position_size()

    def is_trading_allowed(self) -> bool:
        """Check if trading should be allowed based on risk limits"""
        # Stop trading if:
        # 1. Daily loss exceeded
        # 2. Drawdown exceeded
        daily_loss_ok = self.daily_pnl > -self.get_max_daily_loss()
        drawdown_ok = self.current_drawdown < self.get_max_drawdown()

        return daily_loss_ok and drawdown_ok
