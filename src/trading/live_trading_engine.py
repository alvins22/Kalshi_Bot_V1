"""Live trading engine with real order submission and safety rails"""

import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from src.data.models import MarketTick, Signal, Fill, Direction, Outcome, Portfolio, Position
from src.exchanges.kalshi import KalshiClient, KalshiWebSocket
from src.exchanges.kalshi.resilient_client import ResilientKalshiClient
from src.strategies.base_strategy import BaseStrategy, MarketState
from src.utils.trading_logger import TradingLogger, setup_trading_logger
from src.utils.metrics_tracker import MetricsTracker
from src.utils.alert_manager import AlertManager, AlertLevel
from src.trading.trading_config import TradingConfig
from src.trading.order_manager import OrderManager, OrderStatus
from src.trading.safety_rails import SafetyRails


logger = logging.getLogger(__name__)


class LiveTradingEngine:
    """
    Live trading engine with real order submission and comprehensive safety systems

    Key features:
    - Real order submission via REST API
    - Fill reconciliation from WebSocket
    - Safety rails enforcement before each order
    - Comprehensive monitoring and alerting
    - Emergency stop mechanism
    """

    def __init__(
        self,
        config: TradingConfig,
        strategy: BaseStrategy,
        kalshi_client: KalshiClient,
        kalshi_ws: KalshiWebSocket,
    ):
        """
        Initialize live trading engine

        Args:
            config: Trading configuration
            strategy: Strategy for signal generation
            kalshi_client: REST API client for order submission
            kalshi_ws: WebSocket client for fills and market data
        """
        self.config = config
        self.strategy = strategy

        # Wrap client with resilience features if enabled
        api_resilience_config = config.config_dict.get('api_resilience', {})
        if api_resilience_config.get('use_resilient_clients', True):
            try:
                self.kalshi_client = ResilientKalshiClient(
                    api_key=kalshi_client.api_key,
                    private_key_path=kalshi_client.private_key_path,
                    is_demo=kalshi_client.is_demo,
                    timeout=kalshi_client.timeout,
                )
                logger.info("Using ResilientKalshiClient with circuit breaker and rate limiting")
            except Exception as e:
                logger.warning(f"Failed to initialize ResilientKalshiClient: {e}, using base client")
                self.kalshi_client = kalshi_client
        else:
            self.kalshi_client = kalshi_client

        self.kalshi_ws = kalshi_ws
        self.running = False

        # Initialize logging
        self.trading_logger = TradingLogger(
            setup_trading_logger(
                "live_trading",
                log_dir=config.log_dir,
                log_level=config.logging_level,
            )
        )

        # Initialize metrics and alerts
        self.metrics = MetricsTracker(config.initial_capital)
        self.alert_manager = AlertManager(channels=["console"])

        # Initialize portfolio
        self.portfolio = Portfolio(
            timestamp=datetime.utcnow(),
            cash=config.initial_capital,
            positions={},
        )

        # Initialize safety and order management
        risk_limits = config.get_risk_limits()
        self.safety_rails = SafetyRails(risk_limits, config.initial_capital)
        self.order_manager = OrderManager(exchange=config.exchange)

        # Market state tracking
        self.latest_market_state: Dict[str, MarketState] = {}

        logger.info(
            f"Initialized LiveTradingEngine: LIVE {config.strategy_name} on {config.exchange}"
        )

    async def start(self):
        """Start live trading engine"""
        if self.running:
            logger.warning("Engine already running")
            return

        # Verify configuration is for live trading
        if not self.config.is_live():
            logger.error("Configuration is not for live trading")
            return

        logger.critical("=" * 60)
        logger.critical("STARTING LIVE TRADING")
        logger.critical(f"Initial Capital: ${self.config.initial_capital}")
        logger.critical(f"Strategy: {self.config.strategy_name}")
        logger.critical("=" * 60)

        self.running = True

        # Connect WebSocket
        if not await self.kalshi_ws.connect():
            logger.error("Failed to connect WebSocket")
            self.running = False
            return

        self.kalshi_ws.set_on_tick(self._on_market_tick)
        self.kalshi_ws.set_on_fill(self._on_fill)
        self.kalshi_ws.set_on_error(self._on_websocket_error)

        # Subscribe to fills
        await self.kalshi_ws.subscribe_fills()

        # Reconcile positions
        await self._reconcile_positions()

        # Initialize strategy
        self.strategy.initialize({})

        # Start async tasks
        tasks = [
            asyncio.create_task(self._signal_generation_loop()),
            asyncio.create_task(self._order_submission_loop()),
            asyncio.create_task(self._fill_reconciliation_loop()),
            asyncio.create_task(self._metrics_loop()),
            asyncio.create_task(self.kalshi_ws.listen()),
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Live trading engine stopped")
        except Exception as e:
            logger.error(f"Engine error: {e}", exc_info=True)
            self.running = False

    async def stop(self):
        """Graceful shutdown"""
        logger.info("Stopping live trading engine...")
        self.running = False

        # Cancel all open orders
        await self._cancel_all_orders()

        if self.kalshi_ws:
            await self.kalshi_ws.disconnect()

        logger.critical("Live trading engine stopped")

    async def emergency_stop(self, reason: str):
        """Emergency stop trading"""
        logger.critical(f"EMERGENCY STOP: {reason}")
        self.alert_manager.alert_emergency_stop(reason)

        await self.stop()

    async def _reconcile_positions(self):
        """Reconcile positions with exchange"""
        try:
            portfolio = self.kalshi_client.get_portfolio()
            logger.info(
                f"Reconciled portfolio: cash=${portfolio.cash:.2f}, "
                f"balance=${portfolio.balance:.2f}"
            )
            self.portfolio.cash = portfolio.cash
        except Exception as e:
            logger.error(f"Failed to reconcile positions: {e}")

    def _on_market_tick(self, tick: MarketTick):
        """Callback for market tick"""
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

        self.latest_market_state[tick.market_id] = market_state

    def _on_fill(self, fill: Fill):
        """Callback for order fill from WebSocket"""
        asyncio.create_task(self._process_fill(fill))

    def _on_websocket_error(self, error: Exception):
        """Callback for WebSocket errors"""
        logger.error(f"WebSocket error: {error}")
        self.alert_manager.alert_websocket_disconnect()

    async def _signal_generation_loop(self):
        """Generate trading signals from market state"""
        while self.running:
            try:
                all_signals: List[Signal] = []

                for market_id, market_state in self.latest_market_state.items():
                    signals = self.strategy.generate_signals(market_state)

                    for signal in signals:
                        if self.strategy.validate_signal(signal):
                            all_signals.append(signal)
                            self.trading_logger.log_signal(signal)

                if all_signals:
                    logger.debug(f"Generated {len(all_signals)} signals")

                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error in signal generation: {e}")
                await asyncio.sleep(1)

    async def _order_submission_loop(self):
        """Submit orders from pending signals"""
        while self.running:
            try:
                for market_id, market_state in self.latest_market_state.items():
                    signals = self.strategy.generate_signals(market_state)

                    for signal in signals:
                        if not self.strategy.validate_signal(signal):
                            continue

                        # Check safety rails
                        portfolio_value = (
                            self.portfolio.cash
                            + sum(p.total_invested for p in self.portfolio.positions.values())
                        )
                        open_positions = sum(
                            1 for p in self.portfolio.positions.values() if p.contracts > 0
                        )

                        is_safe, error_msg = self.safety_rails.check_signal(
                            signal,
                            market_state,
                            portfolio_value,
                            open_positions,
                        )

                        if not is_safe:
                            logger.warning(f"Signal rejected by safety rails: {error_msg}")
                            continue

                        # Submit order
                        await self._submit_order(signal, market_state)

                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error in order submission: {e}")
                await asyncio.sleep(1)

    async def _submit_order(self, signal: Signal, market_state: MarketState):
        """
        Submit order to exchange

        Args:
            signal: Trading signal
            market_state: Current market state
        """
        try:
            # Create order record
            order = self.order_manager.create_order(signal)

            # Submit to Kalshi API
            response = self.kalshi_client.place_order(
                market_id=signal.market_id,
                side="buy" if signal.direction == Direction.BUY else "sell",
                outcome=signal.outcome.value.lower(),
                contracts=signal.contracts,
                price=signal.estimated_price,
                order_type="limit" if signal.estimated_price else "market",
            )

            order_id = response.get("order_id", order.order_id)
            order.order_id = order_id

            self.order_manager.update_order_status(
                order_id,
                OrderStatus.ACCEPTED,
            )

            logger.info(f"Submitted order: {order_id}")

        except Exception as e:
            logger.error(f"Failed to submit order: {e}")
            self.alert_manager.alert_error(e, {"signal": str(signal)})

    async def _process_fill(self, fill: Fill):
        """
        Process order fill and update portfolio

        Args:
            fill: Fill object from WebSocket
        """
        try:
            # Log fill
            self.trading_logger.log_fill(fill)
            self.alert_manager.alert_fill(fill)

            # Update order status
            self.order_manager.fill_order(
                fill.order_id,
                fill.contracts,
                fill.filled_price,
            )

            # Update portfolio
            key = f"{fill.market_id}:{fill.outcome.value}"

            # Deduct/add cash based on direction
            if fill.direction == Direction.BUY:
                self.portfolio.cash -= fill.total_cost
            else:
                self.portfolio.cash += fill.total_cost

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

            # Update position
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

            # Record metrics
            self.metrics.record_fill(fill)

            # Update strategy
            self.strategy.update_positions([fill])

            logger.debug(f"Processed fill, cash: ${self.portfolio.cash:.2f}")

        except Exception as e:
            logger.error(f"Error processing fill: {e}", exc_info=True)

    async def _fill_reconciliation_loop(self):
        """Periodically reconcile fills with exchange"""
        while self.running:
            try:
                await asyncio.sleep(60)  # Reconcile every 60 seconds

                # Check for abandoned orders
                open_orders = self.order_manager.get_open_orders()
                if open_orders:
                    logger.debug(f"Monitoring {len(open_orders)} open orders")

            except Exception as e:
                logger.error(f"Error in fill reconciliation: {e}")

    async def _metrics_loop(self):
        """Periodic metrics and monitoring"""
        while self.running:
            try:
                # Calculate metrics
                current_pnl = self.portfolio.cash - self.config.initial_capital
                portfolio_value = self.portfolio.cash + sum(
                    p.total_invested for p in self.portfolio.positions.values()
                )

                self.metrics.record_pnl(current_pnl)

                metrics = self.metrics.get_current_metrics()
                metrics.update({
                    "portfolio_value": portfolio_value,
                    "position_count": sum(
                        1 for p in self.portfolio.positions.values() if p.contracts > 0
                    ),
                })

                self.trading_logger.log_heartbeat(metrics)

                # Check safety status
                safety_status = self.safety_rails.get_status()
                if safety_status["emergency_stop_active"]:
                    await self.emergency_stop("Safety limits breached")

                logger.info(
                    f"Portfolio: ${portfolio_value:.2f} | "
                    f"P&L: ${current_pnl:+.2f} | "
                    f"Positions: {metrics['position_count']}"
                )

                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Error in metrics loop: {e}")
                await asyncio.sleep(60)

    async def _cancel_all_orders(self):
        """Cancel all open orders"""
        open_orders = self.order_manager.get_open_orders()

        for order in open_orders:
            try:
                self.kalshi_client.cancel_order(order.order_id)
                self.order_manager.cancel_order(order.order_id)
                logger.info(f"Cancelled order: {order.order_id}")
            except Exception as e:
                logger.error(f"Failed to cancel order {order.order_id}: {e}")

    def get_portfolio(self) -> Portfolio:
        """Get current portfolio"""
        return self.portfolio

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        return self.metrics.get_current_metrics()
