"""Intelligent consensus engine with conflict tracking, regime detection, and Bayesian fusion"""

import logging
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

from src.data.models import Signal, Direction, Outcome

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regimes for strategy weighting"""
    TRENDING = "trending"
    MEAN_REVERTING = "mean_reverting"
    RANGE_BOUND = "range_bound"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"


@dataclass
class ConflictOutcome:
    """Track a signal conflict and its resolution"""
    timestamp: float
    market_id: str
    buy_agents: List[str]
    sell_agents: List[str]
    buy_avg_conf: float
    sell_avg_conf: float
    chosen_direction: Direction
    actual_outcome: Optional[bool] = None  # True if chosen direction was correct
    position_pnl: float = 0.0
    conflict_type: str = ""  # "2v2", "3v1", "1v3", etc


@dataclass
class StrategyStats:
    """Per-strategy performance metrics"""
    name: str
    total_signals: int = 0
    correct_signals: int = 0
    win_rate: float = 0.0

    # Conflict-specific metrics
    conflict_signals: int = 0  # Signals generated during conflicts
    conflict_wins: int = 0  # Times this strategy was in majority during conflict
    conflict_accuracy: float = 0.0  # When in majority, % correct

    # Regime-specific performance
    regime_performance: Dict[str, Dict[str, float]] = field(default_factory=lambda: {})

    def update_conflict_stats(self):
        """Recompute conflict accuracy"""
        if self.conflict_signals > 0:
            self.conflict_accuracy = self.conflict_wins / max(1, self.conflict_signals)


@dataclass
class RegimeMetrics:
    """Market regime tracking"""
    current_regime: MarketRegime = MarketRegime.RANGE_BOUND
    trend_strength: float = 0.0  # -1 (down) to +1 (up)
    reversion_score: float = 0.0  # 0-1, higher = more mean-reverting
    volatility: float = 0.1
    regime_confidence: float = 0.5  # How sure are we about regime
    lookback: int = 50
    price_history: List[float] = field(default_factory=list)

    def update(self, price: float, volatility: float):
        """Update regime metrics with new price"""
        self.price_history.append(price)
        if len(self.price_history) > self.lookback * 2:
            self.price_history = self.price_history[-self.lookback * 2:]
        self.volatility = volatility
        self._detect_regime()

    def _detect_regime(self):
        """Detect current market regime"""
        if len(self.price_history) < 10:
            self.current_regime = MarketRegime.RANGE_BOUND
            return

        prices = np.array(self.price_history)
        returns = np.diff(prices) / prices[:-1]

        # Trend strength: slope of prices
        x = np.arange(len(prices))
        if len(prices) > 1:
            z = np.polyfit(x, prices, 1)
            slope = z[0] / np.mean(prices)  # Normalize
            self.trend_strength = np.clip(slope * 100, -1, 1)

        # Mean reversion: autocorrelation at lag-1
        if len(returns) > 1:
            acf = np.corrcoef(returns[:-1], returns[1:])[0, 1]
            self.reversion_score = max(0, -acf)  # Negative ACF = reversion

        # Volatility regime
        vol = np.std(returns)

        # Detect regime
        abs_trend = abs(self.trend_strength)

        if self.volatility > 0.15:
            self.current_regime = MarketRegime.HIGH_VOLATILITY
            self.regime_confidence = 0.7
        elif self.volatility < 0.05:
            self.current_regime = MarketRegime.LOW_VOLATILITY
            self.regime_confidence = 0.7
        elif abs_trend > 0.3:
            self.current_regime = MarketRegime.TRENDING
            self.regime_confidence = 0.8
        elif self.reversion_score > 0.3:
            self.current_regime = MarketRegime.MEAN_REVERTING
            self.regime_confidence = 0.75
        else:
            self.current_regime = MarketRegime.RANGE_BOUND
            self.regime_confidence = 0.6


class IntelligentConsensusEngine:
    """
    Learning consensus engine with:
    1. Conflict tracking and resolution learning
    2. Regime detection for strategy weighting
    3. Bayesian fusion for signal merging
    """

    def __init__(self):
        self.signal_history = defaultdict(list)
        self.strategy_stats: Dict[str, StrategyStats] = {}
        self.conflict_history: List[ConflictOutcome] = []
        self.regime_metrics: Dict[str, RegimeMetrics] = defaultdict(
            lambda: RegimeMetrics()
        )

        # Regime-aware strategy weights
        # Strategy name -> Regime -> weight
        self.regime_weights: Dict[str, Dict[MarketRegime, float]] = defaultdict(
            lambda: {
                MarketRegime.TRENDING: 0.25,
                MarketRegime.MEAN_REVERTING: 0.25,
                MarketRegime.RANGE_BOUND: 0.25,
                MarketRegime.HIGH_VOLATILITY: 0.25,
                MarketRegime.LOW_VOLATILITY: 0.25,
            }
        )

        # Default regime weights (will adapt during backtesting)
        self._initialize_default_weights()

    def _initialize_default_weights(self):
        """Initialize regime weights based on strategy types"""
        strategy_defaults = {
            'enhanced_matched_pair': {
                MarketRegime.RANGE_BOUND: 0.8,
                MarketRegime.LOW_VOLATILITY: 0.8,
                MarketRegime.TRENDING: 0.2,
                MarketRegime.MEAN_REVERTING: 0.3,
                MarketRegime.HIGH_VOLATILITY: 0.1,
            },
            'improved_momentum': {
                MarketRegime.TRENDING: 0.8,
                MarketRegime.HIGH_VOLATILITY: 0.7,
                MarketRegime.RANGE_BOUND: 0.1,
                MarketRegime.MEAN_REVERTING: 0.2,
                MarketRegime.LOW_VOLATILITY: 0.1,
            },
            'mean_reversion': {
                MarketRegime.MEAN_REVERTING: 0.8,
                MarketRegime.RANGE_BOUND: 0.6,
                MarketRegime.LOW_VOLATILITY: 0.5,
                MarketRegime.TRENDING: 0.1,
                MarketRegime.HIGH_VOLATILITY: 0.3,
            },
            'cross_exchange_arbitrage': {
                MarketRegime.RANGE_BOUND: 0.7,
                MarketRegime.LOW_VOLATILITY: 0.7,
                MarketRegime.TRENDING: 0.3,
                MarketRegime.MEAN_REVERTING: 0.4,
                MarketRegime.HIGH_VOLATILITY: 0.2,
            },
        }

        for strategy, weights in strategy_defaults.items():
            for regime, weight in weights.items():
                self.regime_weights[strategy][regime] = weight
            # Normalize
            total = sum(self.regime_weights[strategy].values())
            for regime in self.regime_weights[strategy]:
                self.regime_weights[strategy][regime] /= total

    def merge_signals_intelligent(
        self,
        signals_by_agent: Dict[str, List[Signal]],
        market_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Signal]:
        """
        Intelligent merge using conflict tracking, regime detection, Bayesian fusion

        Args:
            signals_by_agent: Strategy name -> list of signals
            market_state: Optional market data for regime detection

        Returns:
            market_id -> merged signal
        """
        merged = {}

        # Group by market
        market_signals = defaultdict(list)
        for agent_name, signals in signals_by_agent.items():
            for signal in signals:
                market_signals[signal.market_id].append((agent_name, signal))

        # Process each market
        for market_id, agent_signal_pairs in market_signals.items():
            if not agent_signal_pairs:
                continue

            # Update regime metrics if market state provided
            if market_state and market_id in market_state:
                price = market_state[market_id].get('price', 0.5)
                volatility = market_state[market_id].get('volatility', 0.1)
                self.regime_metrics[market_id].update(price, volatility)

            # Separate buy/sell
            buys = [(a, s) for a, s in agent_signal_pairs if s.direction == Direction.BUY]
            sells = [(a, s) for a, s in agent_signal_pairs if s.direction == Direction.SELL]

            # Get current regime
            regime = self.regime_metrics[market_id].current_regime
            regime_conf = self.regime_metrics[market_id].regime_confidence

            # Resolve conflicts intelligently
            if buys and sells:
                merged_signal = self._resolve_conflict_bayesian(
                    market_id, buys, sells, regime
                )

                # Track the conflict
                if merged_signal:
                    self._track_conflict(
                        market_id, buys, sells, merged_signal.direction
                    )
            else:
                # No conflict: use existing merge
                agent_pairs = buys if buys else sells
                merged_signal = self._consensus_merge(
                    market_id, agent_pairs, regime
                )

            if merged_signal:
                merged[market_id] = merged_signal

        return merged

    def _resolve_conflict_bayesian(
        self,
        market_id: str,
        buys: List[Tuple[str, Signal]],
        sells: List[Tuple[str, Signal]],
        regime: MarketRegime
    ) -> Optional[Signal]:
        """
        Bayesian fusion: treats strategies as noisy signals with calibrated likelihood

        P(buy|data) ∝ P(data|buy) × P(buy)

        Where:
        - P(data|buy) = product of (confidence) for buy signals
        - P(buy) = regime prior + historical accuracy
        """

        # Get strategy confidences
        buy_confs = {agent: sig.confidence for agent, sig in buys}
        sell_confs = {agent: sig.confidence for agent, sig in sells}

        # Get regime-adjusted weights
        buy_weights = {
            agent: self._get_strategy_weight(agent, regime, buy_confs[agent])
            for agent in buy_confs
        }
        sell_weights = {
            agent: self._get_strategy_weight(agent, regime, sell_confs[agent])
            for agent in sell_confs
        }

        # Bayesian likelihood: product of normalized confidences
        buy_likelihood = 1.0
        for agent, conf in buy_confs.items():
            weight = buy_weights[agent]
            # Higher weight + higher confidence = stronger signal
            buy_likelihood *= (conf ** weight)

        sell_likelihood = 1.0
        for agent, conf in sell_confs.items():
            weight = sell_weights[agent]
            sell_likelihood *= (conf ** weight)

        # Normalize to probabilities
        total_likelihood = buy_likelihood + sell_likelihood
        if total_likelihood == 0:
            return None

        p_buy = buy_likelihood / total_likelihood
        p_sell = sell_likelihood / total_likelihood

        # Decision rule with uncertainty handling
        confidence_diff = abs(p_buy - p_sell)

        # If very uncertain (close to 50/50), reduce position or skip
        if confidence_diff < 0.15:
            # Both sides equally likely - high uncertainty
            # Still take position but reduce confidence
            if p_buy > p_sell:
                agent_pairs = buys
                merged_conf = 0.45  # Low confidence
            else:
                agent_pairs = sells
                merged_conf = 0.45
        elif confidence_diff < 0.30:
            # Moderate uncertainty
            agent_pairs = buys if p_buy > p_sell else sells
            merged_conf = 0.60
        else:
            # Clear winner
            agent_pairs = buys if p_buy > p_sell else sells
            merged_conf = min(0.95, 0.70 + (confidence_diff * 0.5))

        # Merge with uncertainty-adjusted confidence
        merged = self._consensus_merge(market_id, agent_pairs, regime)
        if merged:
            merged.confidence = merged_conf
            merged.reason = (
                f"Bayesian({len(buys)}v{len(sells)}) "
                f"P(buy)={p_buy:.2f} conf={merged_conf:.2f}"
            )

        return merged

    def _get_strategy_weight(
        self,
        strategy_name: str,
        regime: MarketRegime,
        confidence: float
    ) -> float:
        """
        Get strategy weight in current regime, adjusted by historical performance
        """
        # Base weight from regime
        regime_weight = self.regime_weights[strategy_name].get(regime, 0.25)

        # Adjust by historical accuracy in this regime
        if strategy_name in self.strategy_stats:
            stats = self.strategy_stats[strategy_name]

            # If we have regime-specific performance, use it
            if regime.value in stats.regime_performance:
                regime_acc = stats.regime_performance[regime.value].get(
                    'win_rate', 0.5
                )
                # Weight higher if strategy performs well in this regime
                regime_weight *= (1.0 + (regime_acc - 0.5))
            else:
                # Fall back to overall win rate
                regime_weight *= max(0.3, stats.win_rate)

        return np.clip(regime_weight, 0.1, 1.0)

    def _consensus_merge(
        self,
        market_id: str,
        agent_pairs: List[Tuple[str, Signal]],
        regime: MarketRegime
    ) -> Optional[Signal]:
        """
        Merge signals from agents on same side, weighted by regime-adjusted strength
        """
        if not agent_pairs:
            return None

        # Get weighted confidences
        agent_names = [agent for agent, _ in agent_pairs]
        signals = [sig for _, sig in agent_pairs]

        weighted_confs = []
        for agent, signal in agent_pairs:
            weight = self._get_strategy_weight(agent, regime, signal.confidence)
            weighted_confs.append(signal.confidence * weight)

        total_weighted_conf = sum(weighted_confs)
        if total_weighted_conf == 0:
            return None

        # Weighted average of contracts
        weighted_contracts = sum(
            signal.confidence * weight * signal.contracts
            for (agent, signal), weight in zip(
                agent_pairs,
                [self._get_strategy_weight(a, regime, s.confidence)
                 for a, s in agent_pairs]
            )
        ) / total_weighted_conf

        # Use highest-confidence agent as base
        base_agent, base_signal = max(agent_pairs, key=lambda x: x[1].confidence)

        # Average confidence across agents
        avg_conf = np.mean([s.confidence for _, s in agent_pairs])

        return Signal(
            timestamp=base_signal.timestamp,
            market_id=market_id,
            strategy_name=f"IntelligentConsensus({len(agent_pairs)},{regime.value})",
            direction=base_signal.direction,
            outcome=base_signal.outcome,
            contracts=int(weighted_contracts),
            confidence=min(0.99, avg_conf),
            reason=f"Merged {agent_names} in {regime.value}",
            estimated_price=base_signal.estimated_price
        )

    def _track_conflict(
        self,
        market_id: str,
        buys: List[Tuple[str, Signal]],
        sells: List[Tuple[str, Signal]],
        chosen_direction: Direction
    ):
        """Track a signal conflict for learning"""
        conflict_type = f"{len(buys)}v{len(sells)}"

        buy_agents = [agent for agent, _ in buys]
        sell_agents = [agent for agent, _ in sells]
        buy_avg_conf = np.mean([s.confidence for _, s in buys])
        sell_avg_conf = np.mean([s.confidence for _, s in sells])

        outcome = ConflictOutcome(
            timestamp=np.random.rand(),  # Will be set by caller if needed
            market_id=market_id,
            buy_agents=buy_agents,
            sell_agents=sell_agents,
            buy_avg_conf=buy_avg_conf,
            sell_avg_conf=sell_avg_conf,
            chosen_direction=chosen_direction,
            conflict_type=conflict_type
        )

        self.conflict_history.append(outcome)

    def record_outcome(
        self,
        conflict_outcome: ConflictOutcome,
        actual_direction: Direction,
        pnl: float = 0.0
    ):
        """
        Record actual outcome of a conflict resolution

        Args:
            conflict_outcome: The conflict that was resolved
            actual_direction: Which direction actually worked
            pnl: Profit/loss from taking this position
        """
        conflict_outcome.actual_outcome = (
            conflict_outcome.chosen_direction == actual_direction
        )
        conflict_outcome.position_pnl = pnl

        # Update strategy stats
        if conflict_outcome.actual_outcome:
            # Chosen side was correct
            for agent in (conflict_outcome.buy_agents
                         if conflict_outcome.chosen_direction == Direction.BUY
                         else conflict_outcome.sell_agents):
                self._update_strategy_stats(
                    agent, correct=True,
                    conflict=True
                )
            # Other side was wrong
            for agent in (conflict_outcome.sell_agents
                         if conflict_outcome.chosen_direction == Direction.BUY
                         else conflict_outcome.buy_agents):
                self._update_strategy_stats(
                    agent, correct=False,
                    conflict=True
                )
        else:
            # Chosen side was wrong
            for agent in (conflict_outcome.buy_agents
                         if conflict_outcome.chosen_direction == Direction.BUY
                         else conflict_outcome.sell_agents):
                self._update_strategy_stats(
                    agent, correct=False,
                    conflict=True
                )
            # Other side was correct
            for agent in (conflict_outcome.sell_agents
                         if conflict_outcome.chosen_direction == Direction.BUY
                         else conflict_outcome.buy_agents):
                self._update_strategy_stats(
                    agent, correct=True,
                    conflict=True
                )

    def _update_strategy_stats(
        self,
        strategy_name: str,
        correct: bool,
        conflict: bool = False
    ):
        """Update strategy performance statistics"""
        if strategy_name not in self.strategy_stats:
            self.strategy_stats[strategy_name] = StrategyStats(name=strategy_name)

        stats = self.strategy_stats[strategy_name]
        stats.total_signals += 1
        if correct:
            stats.correct_signals += 1

        stats.win_rate = stats.correct_signals / max(1, stats.total_signals)

        if conflict:
            stats.conflict_signals += 1
            if correct:
                stats.conflict_wins += 1
            stats.update_conflict_stats()

    def get_intelligence_report(self) -> Dict[str, Any]:
        """Get summary of consensus engine learning"""
        return {
            'total_conflicts': len(self.conflict_history),
            'strategy_stats': {
                name: {
                    'total_signals': stats.total_signals,
                    'win_rate': stats.win_rate,
                    'conflict_signals': stats.conflict_signals,
                    'conflict_accuracy': stats.conflict_accuracy,
                }
                for name, stats in self.strategy_stats.items()
            },
            'regime_metrics': {
                market_id: {
                    'current_regime': metrics.current_regime.value,
                    'trend_strength': float(metrics.trend_strength),
                    'reversion_score': float(metrics.reversion_score),
                    'volatility': float(metrics.volatility),
                }
                for market_id, metrics in self.regime_metrics.items()
            },
            'conflict_resolution_accuracy': self._calculate_conflict_accuracy(),
        }

    def _calculate_conflict_accuracy(self) -> float:
        """Calculate accuracy of conflict resolutions"""
        if not self.conflict_history:
            return 0.0

        resolved = [
            c for c in self.conflict_history
            if c.actual_outcome is not None
        ]
        if not resolved:
            return 0.0

        correct = sum(1 for c in resolved if c.actual_outcome)
        return correct / len(resolved)
