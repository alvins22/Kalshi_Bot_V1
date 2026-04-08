"""Real-time signal profitability tracking and analysis"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
import uuid

from src.data.models import Signal, Outcome

logger = logging.getLogger(__name__)


@dataclass
class SignalMetrics:
    """Metrics for a single signal"""
    signal_id: str
    strategy_name: str
    market_id: str
    outcome: Outcome
    timestamp: datetime
    confidence: float
    contracts: int
    estimated_price: Optional[float]

    # Fill info
    filled: bool = False
    fill_price: Optional[float] = None
    fill_timestamp: Optional[datetime] = None
    fill_slippage: Optional[float] = None  # fill_price - estimated_price

    # Settlement info
    settled: bool = False
    settlement_pnl: Optional[float] = None
    settlement_return: Optional[float] = None  # pnl / (contracts * estimated_price)
    settlement_time: Optional[datetime] = None
    winning_outcome: Optional[Outcome] = None

    @property
    def days_to_settlement(self) -> Optional[float]:
        """Days from signal to settlement"""
        if self.settlement_time and self.timestamp:
            return (self.settlement_time - self.timestamp).total_seconds() / (24 * 3600)
        return None

    @property
    def was_correct(self) -> Optional[bool]:
        """Whether signal prediction was correct"""
        if self.settled and self.winning_outcome:
            return self.outcome == self.winning_outcome
        return None

    @property
    def signal_accuracy(self) -> Optional[float]:
        """Confidence vs actual outcome (1.0 if confident & correct, 0.0 if confident & wrong)"""
        if not self.settled:
            return None

        if self.was_correct:
            return self.confidence
        else:
            return 1.0 - self.confidence


@dataclass
class StrategySignalStats:
    """Aggregated stats for a strategy"""
    strategy_name: str
    total_signals: int = 0
    filled_signals: int = 0
    settled_signals: int = 0
    winning_signals: int = 0

    total_pnl: float = 0.0
    total_invested: float = 0.0
    avg_fill_slippage: float = 0.0

    # Accuracy metrics
    accuracy: float = 0.0  # % of settled signals that were correct
    win_rate: float = 0.0  # Fraction of settled signals that won
    avg_confidence: float = 0.0

    # Risk metrics
    max_loss: float = 0.0
    max_win: float = 0.0
    sharpe_ratio: float = 0.0

    # Time metrics
    avg_days_to_settlement: float = 0.0

    # By market type
    market_stats: Dict[str, dict] = field(default_factory=dict)

    # By outcome
    outcome_stats: Dict[Outcome, dict] = field(default_factory=dict)


class SignalProfitabilityTracker:
    """Track profitability and quality of individual signals"""

    def __init__(self):
        self.signals: Dict[str, SignalMetrics] = {}  # signal_id -> metrics
        self.strategy_stats: Dict[str, StrategySignalStats] = defaultdict(
            lambda: StrategySignalStats(strategy_name="")
        )

        logger.info("Initialized SignalProfitabilityTracker")

    def record_signal(self, signal: Signal) -> str:
        """Record a new signal and return its ID

        Args:
            signal: Signal object

        Returns:
            Unique signal ID for tracking
        """
        signal_id = str(uuid.uuid4())

        metrics = SignalMetrics(
            signal_id=signal_id,
            strategy_name=signal.strategy_name,
            market_id=signal.market_id,
            outcome=signal.outcome,
            timestamp=signal.timestamp,
            confidence=signal.confidence,
            contracts=signal.contracts,
            estimated_price=signal.estimated_price,
        )

        self.signals[signal_id] = metrics

        # Initialize strategy stats if needed
        if signal.strategy_name not in self.strategy_stats:
            self.strategy_stats[signal.strategy_name] = StrategySignalStats(
                strategy_name=signal.strategy_name
            )

        self.strategy_stats[signal.strategy_name].total_signals += 1

        logger.debug(f"Recorded signal {signal_id[:8]} from {signal.strategy_name}")
        return signal_id

    def record_fill(
        self,
        signal_id: str,
        fill_price: float,
        fill_timestamp: datetime,
    ):
        """Record fill execution for a signal

        Args:
            signal_id: Signal ID
            fill_price: Actual fill price
            fill_timestamp: When signal was filled
        """
        if signal_id not in self.signals:
            logger.warning(f"Signal {signal_id} not found for fill recording")
            return

        metrics = self.signals[signal_id]
        metrics.filled = True
        metrics.fill_price = fill_price
        metrics.fill_timestamp = fill_timestamp
        metrics.fill_slippage = fill_price - (metrics.estimated_price or fill_price)

        self.strategy_stats[metrics.strategy_name].filled_signals += 1

        logger.debug(f"Recorded fill for signal {signal_id[:8]}, slippage={metrics.fill_slippage:.4f}")

    def record_settlement(
        self,
        signal_id: str,
        pnl: float,
        winning_outcome: Outcome,
        settlement_time: datetime,
    ):
        """Record market settlement for a signal

        Args:
            signal_id: Signal ID
            pnl: Realized P&L
            winning_outcome: Market outcome (YES or NO)
            settlement_time: When market settled
        """
        if signal_id not in self.signals:
            logger.warning(f"Signal {signal_id} not found for settlement recording")
            return

        metrics = self.signals[signal_id]
        metrics.settled = True
        metrics.settlement_pnl = pnl
        metrics.settlement_time = settlement_time
        metrics.winning_outcome = winning_outcome

        # Calculate settlement return
        if metrics.fill_price and metrics.contracts > 0:
            invested = metrics.contracts * metrics.fill_price
            if invested > 0:
                metrics.settlement_return = pnl / invested

        # Update strategy stats
        strategy_stats = self.strategy_stats[metrics.strategy_name]
        strategy_stats.settled_signals += 1
        strategy_stats.total_pnl += pnl

        if metrics.was_correct:
            strategy_stats.winning_signals += 1

        if pnl < strategy_stats.max_loss:
            strategy_stats.max_loss = pnl
        if pnl > strategy_stats.max_win:
            strategy_stats.max_win = pnl

        logger.debug(
            f"Recorded settlement for signal {signal_id[:8]}, "
            f"pnl={pnl:.2f}, correct={metrics.was_correct}"
        )

    def get_signal_metrics(self, signal_id: str) -> Optional[SignalMetrics]:
        """Get metrics for a specific signal"""
        return self.signals.get(signal_id)

    def get_strategy_stats(self, strategy_name: str) -> Optional[StrategySignalStats]:
        """Get aggregated stats for a strategy

        Args:
            strategy_name: Strategy name

        Returns:
            StrategySignalStats or None if strategy not found
        """
        if strategy_name not in self.strategy_stats:
            return None

        stats = self.strategy_stats[strategy_name]
        self._recalculate_strategy_stats(stats)
        return stats

    def _recalculate_strategy_stats(self, stats: StrategySignalStats):
        """Recalculate aggregated metrics for a strategy"""
        # Get all signals for this strategy
        strategy_signals = [
            m for m in self.signals.values()
            if m.strategy_name == stats.strategy_name
        ]

        if not strategy_signals:
            return

        # Update total signals
        stats.total_signals = len(strategy_signals)
        stats.filled_signals = sum(1 for s in strategy_signals if s.filled)
        stats.settled_signals = sum(1 for s in strategy_signals if s.settled)
        stats.winning_signals = sum(1 for s in strategy_signals if s.was_correct)

        # Calculate accuracy and win rate
        if stats.settled_signals > 0:
            stats.accuracy = stats.winning_signals / stats.settled_signals
            stats.win_rate = stats.accuracy

        # Calculate average confidence
        if strategy_signals:
            stats.avg_confidence = sum(s.confidence for s in strategy_signals) / len(strategy_signals)

        # Calculate average slippage
        filled_signals = [s for s in strategy_signals if s.filled and s.fill_slippage is not None]
        if filled_signals:
            stats.avg_fill_slippage = sum(s.fill_slippage for s in filled_signals) / len(filled_signals)

        # Calculate average days to settlement
        settled_signals = [s for s in strategy_signals if s.settlement_time]
        if settled_signals:
            days_list = [s.days_to_settlement for s in settled_signals if s.days_to_settlement is not None]
            if days_list:
                stats.avg_days_to_settlement = sum(days_list) / len(days_list)

        # Calculate total invested
        stats.total_invested = sum(
            (s.fill_price or s.estimated_price or 0.5) * s.contracts
            for s in filled_signals
        )

        # Calculate Sharpe ratio
        settled_with_pnl = [s for s in strategy_signals if s.settlement_pnl is not None]
        if len(settled_with_pnl) > 1:
            pnls = [s.settlement_pnl for s in settled_with_pnl]
            mean_pnl = sum(pnls) / len(pnls)
            variance = sum((p - mean_pnl) ** 2 for p in pnls) / len(pnls)
            std_dev = variance ** 0.5
            if std_dev > 0:
                stats.sharpe_ratio = mean_pnl / std_dev

    def get_all_strategy_stats(self) -> Dict[str, StrategySignalStats]:
        """Get stats for all strategies"""
        result = {}
        for strategy_name, stats in self.strategy_stats.items():
            self._recalculate_strategy_stats(stats)
            result[strategy_name] = stats
        return result

    def get_signals_by_strategy(self, strategy_name: str) -> List[SignalMetrics]:
        """Get all signals for a strategy"""
        return [s for s in self.signals.values() if s.strategy_name == strategy_name]

    def get_signals_by_market(self, market_id: str) -> List[SignalMetrics]:
        """Get all signals for a market"""
        return [s for s in self.signals.values() if s.market_id == market_id]

    def get_unsettled_signals(self) -> List[SignalMetrics]:
        """Get all unsettled signals"""
        return [s for s in self.signals.values() if not s.settled]

    def get_low_quality_signals(
        self,
        accuracy_threshold: float = 0.45,
        min_settled_signals: int = 20,
    ) -> Dict[str, StrategySignalStats]:
        """Get strategies with accuracy below threshold

        Args:
            accuracy_threshold: Min acceptable accuracy (default 0.45 = 45%)
            min_settled_signals: Minimum settled signals to evaluate (default 20)

        Returns:
            Dict of strategy_name -> stats for low-quality strategies
        """
        low_quality = {}
        for strategy_name, stats in self.get_all_strategy_stats().items():
            if stats.settled_signals >= min_settled_signals:
                if stats.accuracy < accuracy_threshold:
                    low_quality[strategy_name] = stats
        return low_quality

    def get_high_quality_signals(
        self,
        accuracy_threshold: float = 0.55,
        min_settled_signals: int = 10,
    ) -> Dict[str, StrategySignalStats]:
        """Get strategies with accuracy above threshold

        Args:
            accuracy_threshold: Min acceptable accuracy (default 0.55 = 55%)
            min_settled_signals: Minimum settled signals to evaluate (default 10)

        Returns:
            Dict of strategy_name -> stats for high-quality strategies
        """
        high_quality = {}
        for strategy_name, stats in self.get_all_strategy_stats().items():
            if stats.settled_signals >= min_settled_signals:
                if stats.accuracy >= accuracy_threshold:
                    high_quality[strategy_name] = stats
        return high_quality

    def get_recent_signals(
        self,
        strategy_name: Optional[str] = None,
        lookback_hours: int = 24,
    ) -> List[SignalMetrics]:
        """Get signals from recent time period

        Args:
            strategy_name: Optional strategy filter
            lookback_hours: Hours to look back (default 24)

        Returns:
            List of recent signals
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        signals = [
            s for s in self.signals.values()
            if s.timestamp >= cutoff_time
        ]

        if strategy_name:
            signals = [s for s in signals if s.strategy_name == strategy_name]

        return sorted(signals, key=lambda s: s.timestamp, reverse=True)

    def get_dashboard_summary(self) -> Dict:
        """Get summary data for dashboard

        Returns:
            Dictionary with key metrics across all strategies
        """
        all_stats = self.get_all_strategy_stats()
        all_signals = list(self.signals.values())

        total_signals = len(all_signals)
        filled_signals = sum(1 for s in all_signals if s.filled)
        settled_signals = sum(1 for s in all_signals if s.settled)
        winning_signals = sum(1 for s in all_signals if s.was_correct)

        total_pnl = sum(s.settlement_pnl for s in all_signals if s.settlement_pnl is not None)

        return {
            'timestamp': datetime.utcnow(),
            'total_signals': total_signals,
            'filled_signals': filled_signals,
            'settled_signals': settled_signals,
            'winning_signals': winning_signals,
            'overall_accuracy': winning_signals / settled_signals if settled_signals > 0 else 0.0,
            'total_pnl': total_pnl,
            'avg_confidence': sum(s.confidence for s in all_signals) / total_signals if total_signals > 0 else 0.0,
            'low_quality_strategies': self.get_low_quality_signals(),
            'high_quality_strategies': self.get_high_quality_signals(),
            'strategy_stats': all_stats,
        }
