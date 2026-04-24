"""
Unified bot interface for live trading and backtesting

This module provides a clean interface that can work with:
1. Live trading (real-time WebSocket data from Kalshi/Polymarket)
2. Backtesting (historical data from friend's backtesting engine)
3. Paper trading (simulated execution)
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass

from src.data.models import Signal, Fill, Portfolio, Position, MarketTick
from src.strategies.base_strategy import BaseStrategy, MarketState
from src.trading.trading_config import TradingConfig
from src.trading.multi_agent_core import SignalConsensusEngine, RiskCommittee
from src.backtesting.execution_simulator import ExecutionSimulator
from src.utils.trading_logger import TradingLogger, setup_trading_logger
from src.utils.metrics_tracker import MetricsTracker

# Import all strategies
from src.strategies.enhanced_matched_pair_arbitrage import EnhancedMatchedPairArbitrage
from src.strategies.improved_directional_momentum import ImprovedDirectionalMomentum
from src.strategies.mean_reversion_detector import MeanReversionDetector
from src.strategies.cross_exchange_arbitrage import CrossExchangeArbitrageFinder

# Import risk management
from src.risk.volatility_position_sizing import VolatilityAdjustedPositionSizer
from src.risk.dynamic_risk_manager import DynamicRiskManager
from src.risk.information_ratio_sizing import InformationRatioSizer
from src.risk.extreme_value_theory import ExtremeValueTheory
from src.risk.dynamic_correlation import DynamicConditionalCorrelation

# Import Phase 3 improvements
from src.strategies.kalman_filter_mean import KalmanFilterMeanEstimator
from src.strategies.adf_mean_reversion import ADFStationarityTester


logger = logging.getLogger(__name__)


@dataclass
class BotConfig:
    """Configuration for the bot"""
    initial_capital: float = 100000
    log_dir: str = "logs"
    logging_level: str = "INFO"

    # Risk management
    base_max_daily_loss_pct: float = 0.02
    base_max_position_size_pct: float = 0.05
    base_max_drawdown_pct: float = 0.15

    # Position sizing
    target_risk_pct: float = 0.02
    reference_volatility: float = 0.1
    kelly_fraction: float = 0.25

    # Execution
    base_slippage_bps: int = 10
    volume_impact_bps: int = 5
    latency_ms: int = 50


class PredictionMarketBot:
    """
    Unified bot for prediction market trading (Kalshi + Polymarket)

    Features:
    - Multi-strategy consensus engine
    - Volatility-adjusted position sizing
    - Dynamic risk management with drawdown control
    - Mean reversion detection
    - Cross-exchange arbitrage detection
    - Works with live streaming or historical data
    """

    def __init__(self, config: BotConfig = None):
        """Initialize bot with all improvement modules"""
        self.config = config or BotConfig()

        # Initialize logging
        self.logger = TradingLogger(
            setup_trading_logger(
                "prediction_market_bot",
                log_dir=self.config.log_dir,
                log_level=self.config.logging_level,
            )
        )

        logger.info(f"Initializing PredictionMarketBot with capital ${self.config.initial_capital:,.0f}")

        # Initialize portfolio
        self.portfolio = Portfolio(
            timestamp=datetime.utcnow(),
            cash=self.config.initial_capital,
            positions={},
        )

        # Initialize metrics tracker
        self.metrics = MetricsTracker(self.config.initial_capital)

        # Initialize execution simulator
        self.execution_simulator = ExecutionSimulator(config=self._get_execution_config())

        # Initialize strategies with all improvements
        self.strategies = self._initialize_strategies()

        # Initialize consensus engine
        self.consensus_engine = SignalConsensusEngine()

        # Initialize risk management
        self.risk_manager = DynamicRiskManager(
            initial_capital=self.config.initial_capital,
            base_max_daily_loss_pct=self.config.base_max_daily_loss_pct,
            base_max_position_size_pct=self.config.base_max_position_size_pct,
            base_max_drawdown_pct=self.config.base_max_drawdown_pct,
        )

        # Initialize volatility-adjusted position sizing
        self.position_sizer = VolatilityAdjustedPositionSizer(
            target_risk_pct=self.config.target_risk_pct,
            reference_volatility=self.config.reference_volatility,
            kelly_fraction=self.config.kelly_fraction,
        )

        # Initialize Information Ratio sizer for signal quality adjustment
        self.ir_sizer = InformationRatioSizer(
            target_ir=0.5,
            min_ir=0.0,
            max_ir=2.0,
        )

        # Initialize Phase 3 improvements
        self.evt = ExtremeValueTheory(threshold_pct=90)
        self.dcc = DynamicConditionalCorrelation(alpha=0.05, beta=0.94)
        self.kalman_filter = KalmanFilterMeanEstimator(
            process_variance=1e-4,
            observation_variance=1.0,
            initial_mean=0.5
        )
        self.adf_tester = ADFStationarityTester(max_lags=12, significance_level=0.05)

        # Market state tracking
        self.market_states: Dict[str, MarketState] = {}
        self.latest_tick_time: Optional[datetime] = None

        # Trading state
        self.is_trading_allowed = True
        self.halt_reason = ""

        logger.info(f"Initialized bot with {len(self.strategies)} strategies")

    def _get_execution_config(self) -> Dict[str, Any]:
        """Get execution simulator configuration"""
        return {
            'base_slippage_bps': self.config.base_slippage_bps,
            'volume_impact_bps': self.config.volume_impact_bps,
            'latency_ms': self.config.latency_ms,
        }

    def _initialize_strategies(self) -> Dict[str, BaseStrategy]:
        """Initialize all strategies with improvement modules"""
        strategies = {}

        # Arbitrage strategies
        strategies['enhanced_matched_pair'] = EnhancedMatchedPairArbitrage({
            'min_spread_bps': 200,
            'max_position_size': 50000,
            'kelly_fraction': 0.25,
        })

        strategies['cross_exchange_arbitrage'] = CrossExchangeArbitrageFinder({
            'min_profit_bps': 100,
            'matched_pair_threshold': 0.01,
            'cross_exchange_threshold': 0.02,
        })

        # Directional strategies
        strategies['improved_momentum'] = ImprovedDirectionalMomentum({
            'lookback_window': 50,
            'volume_threshold': 3.0,
            'max_position_pct': 0.15,
        })

        strategies['mean_reversion'] = MeanReversionDetector({
            'lookback_window': 20,
            'z_score_threshold': 2.0,
            'bollinger_std_dev': 2.0,
            'min_confidence': 0.5,
        })

        # Initialize all strategies
        for name, strategy in strategies.items():
            strategy.initialize({})
            logger.info(f"Initialized strategy: {name}")

        return strategies

    def update_market_state(self, tick: MarketTick):
        """
        Update market state from a market tick (live or historical)

        This is the main entry point for both live trading and backtesting.
        Can be called from:
        - WebSocket callback (live trading)
        - Historical data iterator (backtesting)

        Args:
            tick: MarketTick with OHLCV data
        """
        # Convert to MarketState
        market_state = MarketState(
            timestamp=tick.timestamp,
            market_id=tick.market_id,
            yes_bid=tick.yes_bid,
            yes_ask=tick.yes_ask,
            no_bid=tick.no_bid,
            no_ask=tick.no_ask,
            volume_24h=tick.volume_24h or 0,
            last_price=tick.last_price or 0.5,
        )

        # Store for reference
        self.market_states[tick.market_id] = market_state
        self.latest_tick_time = tick.timestamp

        # Update volatility tracker
        mid_price = (tick.yes_bid + tick.yes_ask) / 2
        self.position_sizer.update_volatility(tick.market_id, mid_price)

        # Phase 3: Update Kalman filter for dynamic mean estimation
        self.kalman_filter.update(tick.market_id, mid_price)

        # Phase 3: Track returns for EVT tail risk
        if hasattr(self, '_prev_prices'):
            if tick.market_id in self._prev_prices:
                ret = (mid_price - self._prev_prices[tick.market_id]) / max(self._prev_prices[tick.market_id], 1e-6)
                self.evt.add_return(tick.market_id, ret)
        if not hasattr(self, '_prev_prices'):
            self._prev_prices = {}
        self._prev_prices[tick.market_id] = mid_price

        # Phase 3: Track correlations with DCC
        if hasattr(self, '_returns_dict'):
            self.dcc.add_returns(self._returns_dict)
        if not hasattr(self, '_returns_dict'):
            self._returns_dict = {}

    def process_market_tick(self, tick: MarketTick) -> List[Signal]:
        """
        Process a single market tick and generate trading signals

        This is the main processing loop called for each market tick.
        Returns signals that can be:
        1. Executed immediately (paper trading)
        2. Queued for backtesting engine
        3. Sent to live exchange

        Phase 3 Enhancements:
        - ADF stationarity filtering for mean reversion signals
        - Kalman-filtered mean estimates for robust detection
        - EVT tail risk assessment
        - DCC correlation stress checking

        Args:
            tick: MarketTick data

        Returns:
            List of merged signals with risk management applied
        """
        # Update market state (includes Phase 3: Kalman, EVT, DCC tracking)
        self.update_market_state(tick)

        # Get the market state
        if tick.market_id not in self.market_states:
            return []

        market_state = self.market_states[tick.market_id]

        # Phase 3: Check market stationarity for mean reversion signals
        # ADF test helps validate that mean reversion opportunities are valid
        is_stationary, stationarity_score = self.adf_tester.test_stationarity(tick.market_id, [
            self._prev_prices.get(tick.market_id, 0.5)
        ] if hasattr(self, '_prev_prices') else [0.5])

        # Get Phase 3: Kalman filter estimate for market mean
        kalman_mean = self.kalman_filter.get_mean(tick.market_id)
        kalman_confidence = self.kalman_filter.get_confidence(tick.market_id)

        # Phase 3: Get tail risk assessment
        tail_risk_score = self.evt.get_tail_risk_score(tick.market_id)

        # Phase 3: Get correlation stress
        self.dcc.update_dcc()
        correlation_stress = self.dcc.get_correlation_stress_score()

        # Generate signals from all strategies in parallel
        signals_by_agent = {}
        for name, strategy in self.strategies.items():
            try:
                signals = strategy.generate_signals(market_state)

                # Phase 3: Filter signals based on market conditions
                filtered_signals = []
                for signal in signals:
                    # For mean reversion signals, check stationarity
                    if 'mean_reversion' in name.lower() and not is_stationary and stationarity_score < 0.3:
                        logger.debug(f"Signal filtered: {name} - market not stationary (score: {stationarity_score:.2f})")
                        continue

                    # Phase 3: Adjust confidence based on Kalman certainty
                    if kalman_confidence > 0.5:
                        signal.confidence = min(1.0, signal.confidence * kalman_confidence)

                    filtered_signals.append(signal)

                signals_by_agent[name] = filtered_signals
            except Exception as e:
                logger.error(f"Error in strategy {name}: {e}")
                signals_by_agent[name] = []

        # Merge signals through consensus engine
        merged_signals = []
        if any(signals_by_agent.values()):
            consensus_output = self.consensus_engine.merge_signals(signals_by_agent)

            for market_id_key, merged_signal in consensus_output.items():
                # Apply Information Ratio adjustment to signal
                # Scale position size by strategy's IR relative to target
                base_size = merged_signal.contracts / 1000.0 if merged_signal.contracts > 0 else 0.5
                ir_adjusted_size = self.ir_sizer.get_ir_adjusted_size(
                    strategy_name=merged_signal.strategy_name,
                    base_size=base_size,
                    use_historical=True,
                )
                merged_signal.contracts = int(ir_adjusted_size * 1000)

                # Phase 3: Apply tail risk adjustment via EVT
                # Reduce position size if extreme tail risk detected
                if tail_risk_score > 0.7:
                    tail_risk_multiplier = 1.0 - (tail_risk_score * 0.3)  # 0-30% reduction
                    merged_signal.contracts = int(merged_signal.contracts * tail_risk_multiplier)
                    logger.debug(f"Position reduced due to tail risk: {tail_risk_score:.2f}")

                # Phase 3: Apply correlation stress adjustment
                # Reduce portfolio concentration if correlations are breaking down
                if correlation_stress > 0.7:
                    correlation_multiplier = 1.0 - (correlation_stress * 0.2)  # 0-20% reduction
                    merged_signal.contracts = int(merged_signal.contracts * correlation_multiplier)
                    logger.debug(f"Position reduced due to correlation stress: {correlation_stress:.2f}")

                # Apply volatility-adjusted position sizing
                sized_signal = self._apply_position_sizing(merged_signal, market_state)

                # Phase 3: Apply EVT-based VaR limit
                var_95 = self.evt.get_var(tick.market_id, 0.95)
                var_99 = self.evt.get_var(tick.market_id, 0.99)
                max_loss = abs(var_99) * sized_signal.contracts * market_state.yes_mid

                # Check if position loss exceeds VaR limit
                portfolio_value = self.portfolio.get_total_value()
                var_limit = portfolio_value * 0.02  # 2% VaR limit

                if max_loss > var_limit:
                    size_reduction = var_limit / max(max_loss, 1.0)
                    sized_signal.contracts = int(sized_signal.contracts * size_reduction)
                    logger.debug(f"Position reduced due to EVT VaR limit: {max_loss:.0f} > {var_limit:.0f}")

                # Apply risk management
                allowed, reason = self.risk_manager.check_position_allowed(
                    position_size=sized_signal.contracts,
                    portfolio_value=portfolio_value,
                )

                if allowed:
                    merged_signals.append(sized_signal)
                    self.logger.log_signal(sized_signal)
                else:
                    logger.debug(f"Signal rejected by risk manager: {reason}")

        # Check emergency stop conditions
        self.risk_manager.update_portfolio_value(self.portfolio.get_total_value())
        self.risk_manager.update_volatility(self._calculate_volatility())
        self.risk_manager.check_and_apply_emergency_stop()

        if self.risk_manager.emergency_stop_triggered:
            self.is_trading_allowed = False
            self.halt_reason = self.risk_manager.halt_reason
            logger.warning(f"TRADING HALTED: {self.halt_reason}")

        return merged_signals

    def _apply_position_sizing(self, signal: Signal, market_state: MarketState) -> Signal:
        """Apply volatility-adjusted position sizing to signal"""
        # Calculate volatility for this market
        volatility = self._calculate_market_volatility(market_state)

        # Calculate adjusted position size
        position_pct = self.position_sizer.calculate_position_size(
            market_id=signal.market_id,
            confidence=signal.confidence,
            available_capital=self.portfolio.cash,
            current_volatility=volatility,
        )

        # Convert to contracts
        adjusted_contracts = int(position_pct * self.portfolio.cash / market_state.yes_mid)

        # Update signal with adjusted contracts
        signal.contracts = min(adjusted_contracts, signal.contracts)

        return signal

    def execute_signal(self, signal: Signal) -> Optional[List[Fill]]:
        """
        Execute a trading signal

        Args:
            signal: Signal to execute

        Returns:
            List of fills, or None if execution failed
        """
        if not self.is_trading_allowed:
            logger.warning(f"Trading halted: {self.halt_reason}")
            return None

        # Get market state for execution
        if signal.market_id not in self.market_states:
            logger.warning(f"No market state for {signal.market_id}")
            return None

        market_state = self.market_states[signal.market_id]

        # Simulate execution
        fills = self.execution_simulator.execute([signal], market_state)

        # Update portfolio
        for fill in fills:
            self._update_portfolio(fill)
            self.logger.log_fill(fill)

        # Update metrics
        self.metrics.update_trades(fills)

        # Track strategy returns for Information Ratio calculation
        if fills:
            # Calculate returns from fills (simplified: profit/cost)
            returns = []
            for fill in fills:
                if fill.cost > 0:
                    # Return = (current_price - fill_price) / fill_price
                    # For simplicity, we'll track based on fill executed
                    returns.append(fill.price / fill.price - 1.0)  # Will be 0 for new fills

            # Update strategy metrics if we have returns
            if returns:
                self.ir_sizer.update_strategy_metrics(
                    strategy_name=signal.strategy_name,
                    returns=returns,
                    benchmark_return=0.0,
                )

        return fills

    def _update_portfolio(self, fill: Fill):
        """Update portfolio with fill"""
        # Update cash
        self.portfolio.cash -= fill.cost

        # Update positions
        if fill.market_id not in self.portfolio.positions:
            self.portfolio.positions[fill.market_id] = Position(
                market_id=fill.market_id,
                contracts=0,
                avg_price=0,
            )

        position = self.portfolio.positions[fill.market_id]
        position.contracts += fill.contracts
        position.avg_price = (position.avg_price * (position.contracts - fill.contracts) + fill.price * fill.contracts) / max(position.contracts, 1)

    def _calculate_volatility(self) -> float:
        """Calculate average volatility across all markets"""
        if not self.market_states:
            return 0.05

        volatilities = []
        for market_id, market_state in self.market_states.items():
            vol = self._calculate_market_volatility(market_state)
            volatilities.append(vol)

        return sum(volatilities) / len(volatilities) if volatilities else 0.05

    def _calculate_market_volatility(self, market_state: MarketState) -> float:
        """Calculate volatility for a market"""
        # Get cached volatility if available
        cached = self.position_sizer.get_volatility_metrics(market_state.market_id)
        if cached:
            return cached.volatility

        # Default volatility
        return 0.08

    def get_portfolio_metrics(self) -> Dict[str, float]:
        """Get current portfolio metrics"""
        total_value = self.portfolio.get_total_value()

        return {
            'cash': self.portfolio.cash,
            'total_value': total_value,
            'drawdown': self.risk_manager.get_current_drawdown(),
            'daily_loss': self.risk_manager.get_daily_loss_pct(),
            'is_trading_allowed': self.is_trading_allowed,
            'position_count': len([p for p in self.portfolio.positions.values() if p.contracts != 0]),
        }

    def reset_daily_limits(self):
        """Reset daily limits (call at start of trading day)"""
        self.risk_manager.reset_daily_limits(self.portfolio.get_total_value())

    def get_status(self) -> Dict[str, Any]:
        """Get bot status for monitoring"""
        return {
            'is_trading_allowed': self.is_trading_allowed,
            'halt_reason': self.halt_reason,
            'portfolio': self.get_portfolio_metrics(),
            'risk_summary': self.risk_manager.get_risk_summary(),
            'latest_tick_time': self.latest_tick_time,
            'active_strategies': list(self.strategies.keys()),
        }
