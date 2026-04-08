"""Multi-agent paper trading engine with consensus and risk management"""

import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from src.data.models import MarketTick, Signal, Fill, Direction, Outcome, Portfolio, Position
from src.exchanges.kalshi import KalshiClient, KalshiWebSocket
from src.strategies.base_strategy import BaseStrategy, MarketState
from src.backtesting.execution_simulator import ExecutionSimulator
from src.utils.trading_logger import TradingLogger, setup_trading_logger
from src.utils.metrics_tracker import MetricsTracker
from src.trading.trading_config import TradingConfig
from src.trading.multi_agent_core import SignalConsensusEngine, RiskCommittee
from src.risk.portfolio_rebalancer import PortfolioRebalancer


logger = logging.getLogger(__name__)


class MultiAgentPaperTradingEngine:
    """
    Multi-agent paper trading engine combining:
    - Parallel signal generation from multiple strategies
    - Signal consensus merging (conflict resolution)
    - Portfolio-level risk enforcement
    - Realistic execution simulation
    """

    def __init__(
        self,
        config: TradingConfig,
        strategies: Dict[str, BaseStrategy],
        kalshi_client: Optional[KalshiClient] = None,
        kalshi_ws: Optional[KalshiWebSocket] = None,
    ):
        """
        Initialize multi-agent trading engine

        Args:
            config: Trading configuration
            strategies: Dict of strategy_name -> strategy_instance
            kalshi_client: REST API client (created if not provided)
            kalshi_ws: WebSocket client (created if not provided)
        """
        self.config = config
        self.strategies = strategies
        self.running = False

        # Initialize logging
        self.trading_logger = TradingLogger(
            setup_trading_logger(
                "multi_agent_trading",
                log_dir=config.log_dir,
                log_level=config.logging_level,
            )
        )

        # Initialize metrics
        self.metrics = MetricsTracker(config.initial_capital)

        # Initialize portfolio
        self.portfolio = Portfolio(
            timestamp=datetime.utcnow(),
            cash=config.initial_capital,
            positions={},
        )

        # Initialize execution simulator
        self.execution_simulator = ExecutionSimulator()

        # Initialize consensus engine
        self.consensus_engine = SignalConsensusEngine()

        # Initialize risk committee
        risk_limits = config.get_risk_limits()
        self.risk_committee = RiskCommittee(
            max_position=risk_limits.get('max_position_size', 1000),
            max_daily_loss=risk_limits.get('max_daily_loss', 250),
            max_drawdown=risk_limits.get('max_drawdown', 1000),
            max_concentration=risk_limits.get('max_concentration_per_market', 0.20),
        )

        # Initialize portfolio rebalancer
        rebalancing_config = config.config_dict.get('rebalancing', {})
        self.rebalancer = PortfolioRebalancer(rebalancing_config)

        # Initialize exchange clients
        self.kalshi_client = kalshi_client
        self.kalshi_ws = kalshi_ws

        # Market state tracking
        self.latest_market_state: Dict[str, MarketState] = {}
        self.market_filters = config.get_market_filter()

        # Agent performance tracking
        self.agent_stats = {name: {'signals': 0, 'approved': 0} for name in strategies.keys()}

        logger.info(
            f"Initialized MultiAgentPaperTradingEngine with {len(strategies)} agents: "
            f"{', '.join(strategies.keys())}"
        )

    async def start(self):
        """Start multi-agent paper trading engine"""
        if self.running:
            logger.warning("Engine already running")
            return

        self.running = True
        logger.info(
            f"Starting multi-agent paper trading with ${self.portfolio.cash:.2f} "
            f"and {len(self.strategies)} agents"
        )

        # Connect to exchange APIs
        if self.kalshi_ws:
            self.kalshi_ws.set_on_tick(self._on_market_tick)

            if not await self.kalshi_ws.connect():
                logger.error("Failed to connect to WebSocket")
                self.running = False
                return

        # Fetch initial markets
        markets = await self._fetch_markets()
        market_ids = [m.market_id for m in markets[:10]]  # Start with top 10

        # Subscribe to markets
        if self.kalshi_ws and market_ids:
            await self.kalshi_ws.subscribe_ticker(market_ids)

        # Initialize all strategies
        for name, strategy in self.strategies.items():
            try:
                strategy.initialize({})
                logger.info(f"Initialized strategy: {name}")
            except Exception as e:
                logger.error(f"Failed to initialize strategy {name}: {e}")

        # Start async tasks
        tasks = [
            asyncio.create_task(self._signal_generation_loop()),
            asyncio.create_task(self._execution_loop()),
            asyncio.create_task(self._metrics_loop()),
        ]

        if self.kalshi_ws:
            tasks.append(asyncio.create_task(self.kalshi_ws.listen()))

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Multi-agent paper trading engine stopped")
        except Exception as e:
            logger.error(f"Engine error: {e}", exc_info=True)
            self.running = False

    async def stop(self):
        """Stop multi-agent trading engine"""
        self.running = False
        if self.kalshi_ws:
            await self.kalshi_ws.disconnect()
        logger.info("Stopped multi-agent paper trading engine")

    async def _fetch_markets(self) -> list:
        """Fetch available markets from REST API"""
        if not self.kalshi_client:
            logger.warning("No Kalshi REST client available")
            return []

        try:
            markets = self.kalshi_client.get_markets(limit=100)
            logger.info(f"Fetched {len(markets)} markets from API")
            return markets
        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            return []

    def _on_market_tick(self, tick: MarketTick):
        """
        Callback for new market tick from WebSocket

        Args:
            tick: MarketTick data
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

        # Store for strategy processing
        self.latest_market_state[tick.market_id] = market_state

    async def _signal_generation_loop(self):
        """
        Main signal generation loop with consensus merging

        Processes market state and generates trading signals from all agents in parallel,
        then merges through consensus engine.
        """
        while self.running:
            try:
                all_merged_signals: List[Signal] = []

                # Process each market
                for market_id, market_state in list(self.latest_market_state.items()):
                    # Generate signals from all strategies in parallel
                    signal_tasks = {}
                    for name, strategy in self.strategies.items():
                        task = asyncio.create_task(
                            self._generate_strategy_signals(name, strategy, market_state)
                        )
                        signal_tasks[name] = task

                    # Gather all signals
                    signals_by_agent = {}
                    for name, task in signal_tasks.items():
                        try:
                            signals = await asyncio.wait_for(task, timeout=0.5)
                            signals_by_agent[name] = signals
                            self.agent_stats[name]['signals'] += len(signals)
                        except asyncio.TimeoutError:
                            logger.warning(f"Strategy {name} timeout for market {market_id}")
                            signals_by_agent[name] = []
                        except Exception as e:
                            logger.error(f"Error generating signals from {name}: {e}")
                            signals_by_agent[name] = []

                    # Merge signals through consensus engine
                    if any(signals_by_agent.values()):
                        merged_signals = self.consensus_engine.merge_signals(signals_by_agent)

                        for market_id_key, merged_signal in merged_signals.items():
                            # Validate merged signal
                            # Use first strategy's validate method (all should be compatible)
                            first_strategy = next(iter(self.strategies.values()))
                            if first_strategy.validate_signal(merged_signal):
                                all_merged_signals.append(merged_signal)
                                self.trading_logger.log_signal(merged_signal)
                            else:
                                logger.debug(f"Invalid merged signal filtered: {merged_signal}")

                if all_merged_signals:
                    logger.debug(f"Generated {len(all_merged_signals)} merged signals from {len(self.strategies)} agents")

                await asyncio.sleep(1)  # Process every second

            except Exception as e:
                logger.error(f"Error in signal generation loop: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _generate_strategy_signals(
        self, strategy_name: str, strategy: BaseStrategy, market_state: MarketState
    ) -> List[Signal]:
        """
        Generate signals from a single strategy (runs in executor to avoid blocking)

        Args:
            strategy_name: Name of strategy
            strategy: Strategy instance
            market_state: Current market state

        Returns:
            List of signals from this strategy
        """
        try:
            # Run signal generation in executor to avoid blocking
            loop = asyncio.get_event_loop()
            signals = await loop.run_in_executor(
                None,
                strategy.generate_signals,
                market_state
            )
            return signals or []
        except Exception as e:
            logger.error(f"Error generating signals from {strategy_name}: {e}")
            return []

    async def _execution_loop(self):
        """
        Execution loop for simulated fills with risk enforcement

        Uses ExecutionSimulator for realistic fills after RiskCommittee approval.
        """
        pending_signals: List[Signal] = []

        while self.running:
            try:
                # Regenerate signals each cycle
                all_merged_signals: List[Signal] = []

                for market_id, market_state in list(self.latest_market_state.items()):
                    # Generate signals from all strategies
                    signal_tasks = {}
                    for name, strategy in self.strategies.items():
                        task = asyncio.create_task(
                            self._generate_strategy_signals(name, strategy, market_state)
                        )
                        signal_tasks[name] = task

                    signals_by_agent = {}
                    for name, task in signal_tasks.items():
                        try:
                            signals = await asyncio.wait_for(task, timeout=0.5)
                            signals_by_agent[name] = signals or []
                        except (asyncio.TimeoutError, Exception):
                            signals_by_agent[name] = []

                    # Merge signals
                    if any(signals_by_agent.values()):
                        merged_signals = self.consensus_engine.merge_signals(signals_by_agent)
                        all_merged_signals.extend(merged_signals.values())

                # Get portfolio value for risk checks
                portfolio_value = self.portfolio.cash + sum(
                    p.total_invested for p in self.portfolio.positions.values()
                )

                # Check if portfolio rebalancing is needed
                rebalance_needed, rebalance_actions = self.rebalancer.check_rebalance_needed(
                    self.portfolio, datetime.utcnow()
                )

                rebalance_signals = []
                if rebalance_needed and self.latest_market_state:
                    # Generate rebalance signals
                    rebalance_signals = self.rebalancer.generate_rebalance_signals(
                        rebalance_actions, self.portfolio, self.latest_market_state
                    )
                    logger.info(
                        f"Rebalancing needed: {len(rebalance_actions)} actions, "
                        f"generating {len(rebalance_signals)} signals"
                    )

                # Combine strategy signals with rebalance signals
                # Rebalance signals have priority
                combined_signals = rebalance_signals + all_merged_signals

                # Process each signal through risk committee
                approved_signals = []
                for signal in combined_signals:
                    is_approved, reason = self.risk_committee.approve_signal(signal, portfolio_value)

                    if is_approved:
                        approved_signals.append(signal)
                        if signal.strategy_name != 'Rebalancer':
                            self.agent_stats[signal.strategy_name]['approved'] += 1
                        logger.debug(f"Signal approved: {signal.strategy_name} {signal.outcome.value}")
                    else:
                        logger.info(f"Signal rejected: {signal.strategy_name} - {reason}")

                # Execute approved signals
                for signal in approved_signals:
                    market_id = signal.market_id
                    if market_id in self.latest_market_state:
                        market_state = self.latest_market_state[market_id]

                        # Execute via simulator
                        fills = self.execution_simulator.execute([signal], market_state)

                        # Process fills
                        for fill in fills:
                            await self._process_fill(fill)

                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error in execution loop: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _process_fill(self, fill: Fill):
        """
        Process order fill and update portfolio + strategies

        Args:
            fill: Fill object
        """
        try:
            # Log fill
            self.trading_logger.log_fill(fill)

            # Update portfolio
            key = f"{fill.market_id}:{fill.outcome.value}"

            # Deduct from cash
            if fill.direction == Direction.BUY:
                cost = fill.total_cost
                self.portfolio.cash -= cost
            else:
                # Selling: add to cash (simplified)
                revenue = fill.total_cost
                self.portfolio.cash += revenue

            # Update position
            if key not in self.portfolio.positions:
                self.portfolio.positions[key] = Position(
                    market_id=fill.market_id,
                    outcome=fill.outcome,
                    contracts=0,
                    avg_entry_price=fill.filled_price,
                    entry_timestamp=fill.timestamp,
                    total_invested=0.0,
                )

            position = self.portfolio.positions[key]

            # Update position size and price
            if fill.direction == Direction.BUY:
                total_contracts = position.contracts + fill.contracts
                if total_contracts > 0:
                    position.avg_entry_price = (
                        (position.avg_entry_price * position.contracts + fill.filled_price * fill.contracts)
                        / total_contracts
                    )
                position.contracts = total_contracts
                position.total_invested += fill.total_cost
            else:
                position.contracts = max(0, position.contracts - fill.contracts)

            # Record fill for metrics
            self.metrics.record_fill(fill)

            # Update risk committee with position change
            self.risk_committee.update_positions([fill])

            # Update all strategies with fill
            for strategy in self.strategies.values():
                strategy.update_positions([fill])

            logger.debug(
                f"Processed fill: {fill.direction.value} {fill.contracts} "
                f"{fill.outcome.value} @ ${fill.filled_price:.3f}, "
                f"Cash: ${self.portfolio.cash:.2f}"
            )

        except Exception as e:
            logger.error(f"Error processing fill: {e}", exc_info=True)

    async def _metrics_loop(self):
        """
        Periodic metrics tracking loop with multi-agent stats

        Emits P&L, Sharpe ratio, agent performance, and other metrics
        """
        while self.running:
            try:
                # Calculate current metrics
                current_pnl = self.portfolio.cash - self.config.initial_capital
                current_portfolio_value = self.portfolio.cash + sum(
                    p.total_invested for p in self.portfolio.positions.values()
                )

                self.metrics.record_pnl(current_pnl)

                metrics = self.metrics.get_current_metrics()
                metrics.update({
                    "portfolio_value": current_portfolio_value,
                    "position_count": sum(
                        1 for p in self.portfolio.positions.values() if p.contracts > 0
                    ),
                })

                # Add agent statistics
                agent_approval_rates = {}
                for name, stats in self.agent_stats.items():
                    if stats['signals'] > 0:
                        approval_rate = stats['approved'] / stats['signals']
                        agent_approval_rates[f"{name}_approval_rate"] = approval_rate
                        agent_approval_rates[f"{name}_signals"] = stats['signals']

                metrics.update(agent_approval_rates)

                self.trading_logger.log_heartbeat(metrics)

                logger.info(
                    f"Portfolio: ${current_portfolio_value:.2f} | "
                    f"P&L: ${current_pnl:+.2f} | "
                    f"Positions: {metrics['position_count']} | "
                    f"Win Rate: {metrics['win_rate']:.1%} | "
                    f"Agents: {len(self.strategies)}"
                )

                # Log agent performance
                for name, stats in self.agent_stats.items():
                    if stats['signals'] > 0:
                        approval_rate = stats['approved'] / stats['signals']
                        logger.info(
                            f"  Agent {name}: {stats['signals']} signals, "
                            f"{approval_rate:.1%} approval rate"
                        )

                await asyncio.sleep(60)  # Report every 60 seconds

            except Exception as e:
                logger.error(f"Error in metrics loop: {e}", exc_info=True)
                await asyncio.sleep(60)

    def get_portfolio(self) -> Portfolio:
        """Get current portfolio state"""
        return self.portfolio

    def get_metrics(self) -> Dict[str, Any]:
        """Get current trading metrics"""
        metrics = self.metrics.get_current_metrics()
        metrics['agent_stats'] = self.agent_stats
        return metrics

    def get_consensus_scores(self) -> Dict[str, float]:
        """Get consensus engine scores (agent accuracy from wins)"""
        return self.consensus_engine.get_scores()
