"""Advanced dynamic risk management with drawdown prediction and control"""

import numpy as np
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DrawdownEvent:
    """Record of a drawdown event"""
    start_time: datetime
    start_value: float
    min_value: float
    end_time: datetime
    max_drawdown_pct: float
    recovery_time: Optional[timedelta] = None
    recovery_value: Optional[float] = None


@dataclass
class RiskMetrics:
    """Comprehensive risk metrics"""
    timestamp: datetime
    current_value: float
    peak_value: float
    current_drawdown_pct: float
    daily_loss_pct: float
    volatility_pct: float
    value_at_risk_95: float
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    max_drawdown_historical: float = 0.0


class DrawdownPredictor:
    """Predict potential drawdowns based on market conditions"""

    def __init__(self, lookback_bars: int = 100):
        """
        Initialize drawdown predictor

        Args:
            lookback_bars: Number of bars for historical analysis
        """
        self.lookback_bars = lookback_bars
        self.equity_history: List[float] = []
        self.drawdown_events: List[DrawdownEvent] = []
        self.volatility_history: List[float] = []

    def add_equity_point(self, timestamp: datetime, equity_value: float):
        """Add equity snapshot"""
        self.equity_history.append(equity_value)

        if len(self.equity_history) > self.lookback_bars * 2:
            self.equity_history = self.equity_history[-(self.lookback_bars * 2):]

    def add_volatility(self, volatility: float):
        """Add volatility measurement"""
        self.volatility_history.append(volatility)

        if len(self.volatility_history) > self.lookback_bars * 2:
            self.volatility_history = self.volatility_history[-(self.lookback_bars * 2):]

    def predict_drawdown_probability(self) -> float:
        """
        Predict probability of significant drawdown in next period

        Based on:
        - Current volatility vs historical average
        - Recent equity curve slope
        - Distance from previous drawdowns

        Returns:
            Probability 0-1
        """
        if len(self.equity_history) < 10:
            return 0.3  # Default low probability

        recent_equity = np.array(self.equity_history[-20:])
        returns = np.diff(recent_equity) / recent_equity[:-1]

        # High volatility increases drawdown risk
        current_vol = np.std(returns)
        avg_vol = np.mean(self.volatility_history[-20:]) if self.volatility_history else 0.02

        vol_factor = min(1.0, current_vol / max(avg_vol, 0.01))

        # Negative slope (losing money) increases risk
        slope = (recent_equity[-1] - recent_equity[0]) / len(recent_equity)
        slope_factor = max(0.0, -slope / recent_equity[0])

        # Combine factors
        drawdown_probability = 0.5 * vol_factor + 0.5 * slope_factor

        return np.clip(drawdown_probability, 0.0, 1.0)

    def get_predicted_max_drawdown(self) -> float:
        """
        Predict maximum drawdown based on historical patterns

        Returns:
            Predicted max drawdown as percentage (0-1)
        """
        if not self.drawdown_events:
            return 0.10  # Default 10% if no history

        drawdowns = [event.max_drawdown_pct for event in self.drawdown_events]
        current_vol_ratio = (
            np.std(self.volatility_history[-20:]) / np.mean(self.volatility_history[-20:])
            if self.volatility_history
            else 1.0
        )

        predicted = np.mean(drawdowns) * current_vol_ratio

        return np.clip(predicted, 0.05, 0.50)


class DynamicRiskManager:
    """Manage dynamic risk limits and emergency stops"""

    def __init__(
        self,
        initial_capital: float = 100000,
        base_max_daily_loss_pct: float = 0.02,
        base_max_position_size_pct: float = 0.05,
        base_max_drawdown_pct: float = 0.15,
    ):
        """
        Initialize dynamic risk manager

        Args:
            initial_capital: Starting capital
            base_max_daily_loss_pct: Base max daily loss (% of capital)
            base_max_position_size_pct: Base max position size (% of portfolio)
            base_max_drawdown_pct: Base max allowed drawdown (% of peak)
        """
        self.initial_capital = initial_capital
        self.base_max_daily_loss_pct = base_max_daily_loss_pct
        self.base_max_position_size_pct = base_max_position_size_pct
        self.base_max_drawdown_pct = base_max_drawdown_pct

        self.current_value = initial_capital
        self.peak_value = initial_capital
        self.daily_start_value = initial_capital
        self.daily_pnl = 0.0

        self.drawdown_predictor = DrawdownPredictor()
        self.risk_metrics_history: List[RiskMetrics] = []

        self.emergency_stop_triggered = False
        self.trading_halted = False
        self.halt_reason = ""

    def update_portfolio_value(self, new_value: float):
        """Update current portfolio value"""
        self.current_value = new_value
        self.peak_value = max(self.peak_value, new_value)
        self.daily_pnl = new_value - self.daily_start_value

        # Add to equity history
        self.drawdown_predictor.add_equity_point(datetime.utcnow(), new_value)

    def update_volatility(self, volatility: float):
        """Update market volatility estimate"""
        self.drawdown_predictor.add_volatility(volatility)

    def get_current_drawdown(self) -> float:
        """Get current drawdown as percentage"""
        if self.peak_value <= 0:
            return 0.0
        return (self.peak_value - self.current_value) / self.peak_value

    def get_daily_loss_pct(self) -> float:
        """Get daily loss as percentage of capital"""
        if self.daily_start_value <= 0:
            return 0.0
        return self.daily_pnl / self.daily_start_value

    def calculate_dynamic_limits(self) -> Dict[str, float]:
        """
        Calculate dynamic risk limits based on current conditions

        Returns:
            Dict with: max_position_size, max_daily_loss, max_drawdown
        """
        current_drawdown = self.get_current_drawdown()
        volatility_adjustment = self.drawdown_predictor.volatility_history[-1] / 0.1 if self.drawdown_predictor.volatility_history else 1.0
        drawdown_risk = self.drawdown_predictor.predict_drawdown_probability()

        # Adjust limits based on drawdown (scale down as drawdown increases)
        drawdown_factor = 1.0 - current_drawdown

        # Adjust limits based on volatility (scale down in high-volatility regimes)
        volatility_factor = 1.0 / volatility_adjustment

        # Adjust based on predicted drawdown risk
        risk_factor = 1.0 - drawdown_risk

        # Combined adjustment
        adjustment = drawdown_factor * volatility_factor * risk_factor

        limits = {
            "max_position_size_pct": self.base_max_position_size_pct * adjustment,
            "max_daily_loss_pct": self.base_max_daily_loss_pct * adjustment,
            "max_drawdown_pct": self.base_max_drawdown_pct,
        }

        return limits

    def check_position_allowed(self, position_size: float, portfolio_value: float) -> Tuple[bool, str]:
        """
        Check if new position is allowed

        Args:
            position_size: Size of proposed position
            portfolio_value: Current portfolio value

        Returns:
            (allowed, reason)
        """
        if self.emergency_stop_triggered:
            return False, "Emergency stop triggered"

        if self.trading_halted:
            return False, f"Trading halted: {self.halt_reason}"

        limits = self.calculate_dynamic_limits()
        position_pct = position_size / portfolio_value

        if position_pct > limits["max_position_size_pct"]:
            return (
                False,
                f"Position {position_pct:.1%} exceeds limit {limits['max_position_size_pct']:.1%}",
            )

        return True, "OK"

    def check_emergency_stop(self) -> Tuple[bool, str]:
        """
        Check if emergency stop conditions triggered

        Returns:
            (stop_triggered, reason)
        """
        current_drawdown = self.get_current_drawdown()
        daily_loss = self.get_daily_loss_pct()
        limits = self.calculate_dynamic_limits()

        # Daily loss threshold
        if daily_loss < -limits["max_daily_loss_pct"]:
            return True, f"Daily loss {daily_loss:.1%} exceeds limit {-limits['max_daily_loss_pct']:.1%}"

        # Drawdown threshold
        if current_drawdown > limits["max_drawdown_pct"]:
            return True, f"Drawdown {current_drawdown:.1%} exceeds limit {limits['max_drawdown_pct']:.1%}"

        # Predicted high drawdown risk
        predicted_dd = self.drawdown_predictor.get_predicted_max_drawdown()
        if predicted_dd > 0.25 and self.drawdown_predictor.predict_drawdown_probability() > 0.8:
            return True, f"High predicted drawdown risk: {predicted_dd:.1%}"

        return False, ""

    def check_and_apply_emergency_stop(self):
        """Check emergency stop conditions and apply if triggered"""
        stop_triggered, reason = self.check_emergency_stop()

        if stop_triggered:
            self.emergency_stop_triggered = True
            self.halt_reason = reason
            logger.critical(f"EMERGENCY STOP TRIGGERED: {reason}")

    def reset_daily_limits(self, new_day_start_value: float):
        """Reset daily limits at start of new day"""
        self.daily_start_value = new_day_start_value
        self.daily_pnl = 0.0

    def halt_trading(self, reason: str):
        """Manually halt trading"""
        self.trading_halted = True
        self.halt_reason = reason
        logger.warning(f"Trading halted: {reason}")

    def resume_trading(self):
        """Resume trading after halt"""
        self.trading_halted = False
        self.halt_reason = ""
        logger.info("Trading resumed")

    def calculate_risk_metrics(self) -> RiskMetrics:
        """Calculate comprehensive risk metrics"""
        if len(self.drawdown_predictor.equity_history) < 2:
            return RiskMetrics(
                timestamp=datetime.utcnow(),
                current_value=self.current_value,
                peak_value=self.peak_value,
                current_drawdown_pct=0.0,
                daily_loss_pct=0.0,
                volatility_pct=0.0,
                value_at_risk_95=0.0,
            )

        equity_array = np.array(self.drawdown_predictor.equity_history[-100:])
        returns = np.diff(equity_array) / equity_array[:-1]

        volatility = np.std(returns) if len(returns) > 1 else 0.0

        # Value at Risk (95%)
        var_95 = np.percentile(returns, 5)

        # Sharpe ratio
        sharpe = None
        if volatility > 0:
            mean_return = np.mean(returns)
            sharpe = mean_return / volatility if volatility > 0 else None

        # Sortino ratio (only downside volatility)
        sortino = None
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0:
            downside_vol = np.std(downside_returns)
            mean_return = np.mean(returns)
            if downside_vol > 0:
                sortino = mean_return / downside_vol

        metrics = RiskMetrics(
            timestamp=datetime.utcnow(),
            current_value=self.current_value,
            peak_value=self.peak_value,
            current_drawdown_pct=self.get_current_drawdown(),
            daily_loss_pct=self.get_daily_loss_pct(),
            volatility_pct=volatility,
            value_at_risk_95=var_95,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown_historical=max([0.0] + [self.get_current_drawdown()]),
        )

        self.risk_metrics_history.append(metrics)

        return metrics

    def get_risk_summary(self) -> Dict:
        """Get current risk summary"""
        return {
            "current_value": self.current_value,
            "peak_value": self.peak_value,
            "drawdown_pct": self.get_current_drawdown(),
            "daily_loss_pct": self.get_daily_loss_pct(),
            "emergency_stop_triggered": self.emergency_stop_triggered,
            "trading_halted": self.trading_halted,
            "dynamic_limits": self.calculate_dynamic_limits(),
            "predicted_dd_probability": self.drawdown_predictor.predict_drawdown_probability(),
        }
