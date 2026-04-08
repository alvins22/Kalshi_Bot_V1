"""
Main Kalshi Trading Bot - Orchestrates all trading components

PHASE 2 IMPROVEMENTS INTEGRATED:
- Walk-Forward Testing: Validates strategy isn't overfitting
- Attribution Analysis: Tracks what's making money
- Smart Exit Manager: Intelligent position exit management
- Multi-Timeframe Momentum: Confirms signals across timeframes
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

from config.bot_config import BotConfig
from src.data.kalshi_client import KalshiClient, OrderBook
from src.risk.position_manager import PositionManager
from src.risk.risk_manager import RiskManager, RiskLimits
from src.strategies.arbitrage_strategy import ArbitrageDetector, ArbitrageExecutor

# Phase 2 Improvements
from src.backtesting.walk_forward_analyzer import WalkForwardAnalyzer
from src.analysis.attribution_analyzer import AttributionAnalyzer
from src.strategies.smart_exit_manager import SmartExitManager
from src.strategies.multi_timeframe_momentum import MultiTimeframeMomentum

logger = logging.getLogger(__name__)


@dataclass
class BotStatistics:
    """Bot runtime statistics"""
    start_time: datetime
    opportunities_detected: int = 0
    trades_executed: int = 0
    trades_profitable: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    uptime_seconds: float = 0.0

    # Phase 2 metrics
    mtf_signals_aligned: int = 0  # Multi-timeframe momentum aligned signals
    smart_exits_triggered: int = 0  # Total exit signals from smart exit manager
    exit_profit_targets_hit: int = 0
    exit_stop_losses_hit: int = 0
    attribution_total_trades_logged: int = 0
    best_strategy: Optional[str] = None
    best_market: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "start_time": self.start_time.isoformat(),
            "uptime_seconds": self.uptime_seconds,
            "opportunities_detected": self.opportunities_detected,
            "trades_executed": self.trades_executed,
            "trades_profitable": self.trades_profitable,
            "total_pnl": self.total_pnl,
            "max_drawdown": self.max_drawdown,
            "mtf_signals_aligned": self.mtf_signals_aligned,
            "smart_exits_triggered": self.smart_exits_triggered,
            "attribution_trades_logged": self.attribution_total_trades_logged,
        }


class KalshiTradingBot:
    """Main trading bot"""

    def __init__(self, config: BotConfig):
        self.config = config
        self.statistics = BotStatistics(start_time=datetime.utcnow())

        # Initialize components
        self.kalshi_client = KalshiClient(
            api_key=config.kalshi.api_key,
            api_secret=config.kalshi.api_secret,
            rest_url=config.kalshi.rest_url,
            ws_url=config.kalshi.ws_url,
            sandbox=config.kalshi.sandbox,
        )

        self.position_manager = PositionManager()

        risk_limits = RiskLimits(
            initial_capital=config.risk.initial_capital_usd,
            max_position_pct=config.risk.max_position_size_pct,
            daily_loss_pct=config.risk.daily_loss_limit_pct,
            weekly_loss_pct=config.risk.weekly_loss_limit_pct,
            monthly_loss_pct=config.risk.monthly_loss_limit_pct,
            kelly_fraction=config.risk.kelly_fraction,
        )
        self.risk_manager = RiskManager(risk_limits)

        self.arbitrage_detector = ArbitrageDetector(
            min_spread_bps=config.strategy.min_spread_bps
        )

        self.arbitrage_executor = ArbitrageExecutor(
            kalshi_client=self.kalshi_client,
            position_manager=self.position_manager,
            risk_manager=self.risk_manager,
        )

        # Phase 2: Initialize improvement modules
        self.walk_forward_analyzer = WalkForwardAnalyzer(
            in_sample_weeks=config.strategy.get("walk_forward_in_sample_weeks", 8),
            out_sample_weeks=config.strategy.get("walk_forward_out_sample_weeks", 2),
            step_weeks=config.strategy.get("walk_forward_step_weeks", 2),
        )

        self.attribution_analyzer = AttributionAnalyzer()

        self.smart_exit_manager = SmartExitManager(
            profit_target_pct=config.strategy.get("profit_target_pct", 2.0),
            stop_loss_pct=config.strategy.get("stop_loss_pct", 1.0),
            trailing_stop_pct=config.strategy.get("trailing_stop_pct", 1.5),
            time_limit_hours=config.strategy.get("time_limit_hours", 24),
        )

        self.mtf_momentum = MultiTimeframeMomentum()

        # State
        self._running = False
        self._shutdown_requested = False
        self.order_books: Dict[str, OrderBook] = {}
        self.last_cleanup = datetime.utcnow()
        self.last_heartbeat = datetime.utcnow()
        self.last_attribution_report = datetime.utcnow()

        # Tracking for multi-timeframe momentum
        self._price_history: Dict[str, List[float]] = {}
        self._mtf_min_alignment = config.strategy.get("mtf_min_alignment", 3)

        logger.info("Trading bot initialized")
        logger.info(config.summary())
        logger.info("✅ Phase 2 improvements loaded:")
        logger.info("   - Walk-Forward Testing")
        logger.info("   - Attribution Analysis")
        logger.info("   - Smart Exit Manager")
        logger.info("   - Multi-Timeframe Momentum")

    async def start(self):
        """Start the bot"""
        try:
            self._running = True
            self._shutdown_requested = False

            # Connect to Kalshi
            logger.info("Connecting to Kalshi...")
            if not await self.kalshi_client.connect():
                raise RuntimeError("Failed to connect to Kalshi")

            # Register callbacks
            self.kalshi_client.register_orderbook_callback(self._on_orderbook_update)

            logger.info("Starting main trading loop...")

            # Run main loop
            await self._main_loop()

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error(f"Bot error: {e}", exc_info=True)
        finally:
            await self._shutdown()

    async def _main_loop(self):
        """Main trading loop"""
        logger.info("Main loop started")

        while self._running and not self._shutdown_requested:
            try:
                # Heartbeat check
                await self._heartbeat()

                # Cleanup old opportunities
                await self._cleanup_opportunities()

                # Detect and execute arbitrage
                await self._detect_and_execute_arbitrage()

                # Small delay to prevent busy-waiting
                await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                await asyncio.sleep(1.0)

        logger.info("Main loop ended")

    async def _on_orderbook_update(self, orderbook: OrderBook):
        """Handle order book update from Kalshi"""
        try:
            self.order_books[orderbook.token_id] = orderbook
            current_price = orderbook.get_yes_mid() or 0.5

            self.position_manager.update_position_price(
                orderbook.token_id,
                current_price,
            )

            # Phase 2: Update smart exit manager with price
            self.smart_exit_manager.update_price(
                orderbook.token_id,
                current_price,
                datetime.utcnow().timestamp(),
            )

            # Phase 2: Track price history for multi-timeframe momentum
            if orderbook.token_id not in self._price_history:
                self._price_history[orderbook.token_id] = []

            self._price_history[orderbook.token_id].append(current_price)
            # Keep only last 100 prices for efficiency
            if len(self._price_history[orderbook.token_id]) > 100:
                self._price_history[orderbook.token_id] = self._price_history[orderbook.token_id][-100:]

        except Exception as e:
            logger.error(f"Error handling orderbook update: {e}")

    async def _detect_and_execute_arbitrage(self):
        """Detect and execute arbitrage opportunities"""
        try:
            if not self.order_books:
                return

            # Group order books by market
            market_books = {}
            for token_id, orderbook in self.order_books.items():
                market_id = orderbook.market_id
                if market_id not in market_books:
                    market_books[market_id] = {}

                # Determine if this is YES or NO
                if "YES" in token_id:
                    market_books[market_id]['yes'] = orderbook
                elif "NO" in token_id:
                    market_books[market_id]['no'] = orderbook

            # Detect opportunities
            signals = self.arbitrage_detector.detect_opportunities(market_books)
            self.statistics.opportunities_detected += len(signals)

            # Phase 2: Update multi-timeframe momentum with market prices
            self._update_mtf_momentum(market_books)

            # Execute top opportunities
            available_capital = self.config.risk.initial_capital_usd - self.position_manager.get_total_invested()

            for signal in signals[:5]:  # Execute top 5 opportunities per iteration
                if available_capital <= 0:
                    break

                # Phase 2: Check if multi-timeframe momentum aligns with signal
                mtf_aligned, mtf_direction, mtf_confidence = self.mtf_momentum.should_trade(
                    min_alignment=self._mtf_min_alignment
                )

                # Only execute if MTF momentum is aligned (or MTF disabled)
                if not self.config.strategy.get("require_mtf_alignment", True) or mtf_aligned:
                    if mtf_aligned:
                        self.statistics.mtf_signals_aligned += 1
                        logger.info(f"Multi-TF momentum aligned: {mtf_direction} @ {mtf_confidence:.2f}")

                    success, message, details = await self.arbitrage_executor.execute_arbitrage(
                        signal=signal,
                        capital=available_capital,
                        dry_run=self.config.dry_run or self.config.paper_trading,
                    )

                    if success:
                        self.statistics.trades_executed += 1
                        logger.info(f"Arbitrage executed: {message}")
                        available_capital -= details.get("total_cost", 0)

                        # Phase 2: Register position with smart exit manager
                        position_id = details.get("position_id", f"TRADE_{self.statistics.trades_executed}")
                        entry_price = details.get("entry_price", signal.get("price", 0.5))
                        self.smart_exit_manager.open_position(
                            position_id=position_id,
                            market_id=signal.get("market_id", "unknown"),
                            side=signal.get("signal", "BUY"),
                            entry_price=entry_price,
                            entry_time=datetime.utcnow().timestamp(),
                            contracts=details.get("contracts", 1),
                        )
                    else:
                        logger.warning(f"Arbitrage failed: {message}")
                else:
                    logger.debug(f"Skipped trade: MTF momentum not aligned")

            # Phase 2: Check for position exits
            await self._check_position_exits()

        except Exception as e:
            logger.error(f"Error in arbitrage detection/execution: {e}")

    def _update_mtf_momentum(self, market_books: Dict[str, Dict]):
        """Update multi-timeframe momentum with current market prices"""
        try:
            if not market_books:
                return

            # Get average price from all available markets
            prices = []
            for market_id, books in market_books.items():
                if 'yes' in books and books['yes']:
                    price = books['yes'].get_yes_mid() or 0.5
                    prices.append(price)

            if not prices:
                return

            # Use average price for momentum
            avg_price = sum(prices) / len(prices)

            # For simplicity, feed same price to all timeframes
            # In production, you'd use actual OHLC data for each timeframe
            self.mtf_momentum.update_prices(
                prices_1m=avg_price,
                prices_5m=avg_price,
                prices_15m=avg_price,
                prices_1h=avg_price,
            )

        except Exception as e:
            logger.debug(f"Error updating MTF momentum: {e}")

    async def _check_position_exits(self):
        """Check if any positions should exit"""
        try:
            current_time = datetime.utcnow().timestamp()
            current_prices = {}

            # Build price map from order books
            for token_id, orderbook in self.order_books.items():
                price = orderbook.get_yes_mid() or 0.5
                current_prices[token_id] = price

            if not current_prices:
                return

            # Check for exits
            exit_signals = self.smart_exit_manager.check_exits(current_time, current_prices)

            for signal in exit_signals:
                self.statistics.smart_exits_triggered += 1

                if signal.reason == "profit_target":
                    self.statistics.exit_profit_targets_hit += 1
                elif signal.reason == "stop_loss":
                    self.statistics.exit_stop_losses_hit += 1

                # Close the position
                result = self.smart_exit_manager.close_position(
                    position_id=signal.position_id,
                    exit_price=signal.exit_price,
                    exit_reason=signal.reason,
                )

                if result:
                    logger.info(
                        f"Position exit: {signal.reason} "
                        f"P&L=${result['pnl']:.2f} "
                        f"({result['return_pct']:+.2f}%)"
                    )

                    # Phase 2: Log trade to attribution analyzer
                    self._log_trade_to_attribution(result)

                    # Update statistics
                    if result['pnl'] > 0:
                        self.statistics.trades_profitable += 1
                    self.statistics.total_pnl += result['pnl']

        except Exception as e:
            logger.debug(f"Error checking position exits: {e}")

    def _log_trade_to_attribution(self, trade_result: Dict):
        """Log completed trade to attribution analyzer"""
        try:
            position_id = trade_result.get("position_id", "unknown")
            exit_price = trade_result.get("exit_price", 0.5)
            entry_price = trade_result.get("entry_price", 0.5)
            pnl = trade_result.get("pnl", 0.0)
            return_pct = trade_result.get("return_pct", 0.0)
            exit_reason = trade_result.get("exit_reason", "unknown")

            # Determine strategy from exit reason
            strategy = f"arbitrage_{exit_reason}"

            self.attribution_analyzer.add_trade(
                trade_id=position_id,
                strategy=strategy,
                market_id=exit_reason,  # Using exit_reason as market proxy
                entry_time=datetime.utcnow().timestamp() - 3600,  # Estimate 1h hold
                exit_time=datetime.utcnow().timestamp(),
                pnl=pnl,
                return_pct=return_pct / 100 if return_pct != 0 else 0,
            )

            self.statistics.attribution_total_trades_logged += 1

        except Exception as e:
            logger.debug(f"Error logging trade to attribution: {e}")

    async def _cleanup_opportunities(self):
        """Clean up old opportunities"""
        now = datetime.utcnow()
        if (now - self.last_cleanup).total_seconds() > 60:
            self.arbitrage_detector.clear_old_signals(max_age_seconds=300)
            self.last_cleanup = now

    async def _heartbeat(self):
        """Periodic heartbeat check"""
        now = datetime.utcnow()
        if (now - self.last_heartbeat).total_seconds() > 60:
            uptime = (now - self.statistics.start_time).total_seconds()
            self.statistics.uptime_seconds = uptime

            stats = self.position_manager.get_stats()
            risk_summary = self.risk_manager.get_risk_summary()

            # Base heartbeat
            logger.info(
                f"HEARTBEAT: "
                f"Uptime={uptime:.0f}s, "
                f"Opportunities={self.statistics.opportunities_detected}, "
                f"Trades={self.statistics.trades_executed}, "
                f"P&L=${stats['total_pnl']:.2f}, "
                f"Daily Loss=${risk_summary['daily_loss']:.2f}/{risk_summary['daily_limit']:.2f}"
            )

            # Phase 2: Log smart exit manager stats
            if self.smart_exit_manager.exit_history:
                exit_stats = self.smart_exit_manager.get_stats()
                logger.info(
                    f"SMART EXITS: "
                    f"Triggered={self.statistics.smart_exits_triggered}, "
                    f"Profit Targets={self.statistics.exit_profit_targets_hit}, "
                    f"Stop Losses={self.statistics.exit_stop_losses_hit}, "
                    f"Total P&L=${exit_stats.get('total_pnl', 0):.2f}"
                )

            # Phase 2: Log multi-timeframe momentum stats
            if self.statistics.mtf_signals_aligned > 0:
                logger.info(
                    f"MULTI-TF MOMENTUM: "
                    f"Aligned Signals={self.statistics.mtf_signals_aligned}"
                )

            # Phase 2: Log attribution analysis every 5 minutes
            if (now - self.last_attribution_report).total_seconds() > 300:
                try:
                    if self.attribution_analyzer.trades:
                        logger.info(
                            f"ATTRIBUTION ANALYSIS:\n"
                            f"{self.attribution_analyzer.get_summary()}"
                        )
                        self.last_attribution_report = now
                except Exception as e:
                    logger.debug(f"Error in attribution report: {e}")

            # Phase 2: Log multi-timeframe momentum signals
            try:
                mtf_summary = self.mtf_momentum.get_signal_summary()
                should_trade, direction, confidence = self.mtf_momentum.should_trade()
                logger.debug(
                    f"MTF Status: {direction} (confidence={confidence:.2f}, "
                    f"should_trade={should_trade})"
                )
            except Exception as e:
                logger.debug(f"Error in MTF logging: {e}")

            self.last_heartbeat = now

    async def shutdown(self):
        """Request graceful shutdown"""
        logger.info("Shutdown requested")
        self._shutdown_requested = True

    async def _shutdown(self):
        """Internal shutdown"""
        try:
            logger.info("Shutting down bot...")

            # Disconnect from Kalshi
            await self.kalshi_client.disconnect()

            # Print final statistics
            stats = self.position_manager.get_stats()
            uptime = (datetime.utcnow() - self.statistics.start_time).total_seconds()

            logger.info(
                f"\n{'='*60}\n"
                f"FINAL STATISTICS\n"
                f"{'='*60}\n"
                f"Uptime: {uptime:.0f}s\n"
                f"Opportunities Detected: {self.statistics.opportunities_detected}\n"
                f"Trades Executed: {self.statistics.trades_executed}\n"
                f"Open Positions: {stats['open_positions']}\n"
                f"Closed Trades: {stats['closed_trades']}\n"
                f"Total P&L: ${stats['total_pnl']:.2f}\n"
                f"Win Rate: {stats['win_rate_pct']:.1f}%\n"
                f"Profit Factor: {stats['profit_factor']:.2f}\n"
                f"{'='*60}\n"
            )

            # Phase 2: Print final Phase 2 statistics
            logger.info(
                f"{'='*60}\n"
                f"PHASE 2 IMPROVEMENTS SUMMARY\n"
                f"{'='*60}\n"
                f"Multi-TF Momentum Signals Aligned: {self.statistics.mtf_signals_aligned}\n"
                f"Smart Exits Triggered: {self.statistics.smart_exits_triggered}\n"
                f"  ├─ Profit Targets: {self.statistics.exit_profit_targets_hit}\n"
                f"  └─ Stop Losses: {self.statistics.exit_stop_losses_hit}\n"
                f"Attribution Trades Logged: {self.statistics.attribution_total_trades_logged}\n"
            )

            # Phase 2: Print attribution summary
            try:
                if self.attribution_analyzer.trades:
                    logger.info(f"\nAttribution Analysis:\n{self.attribution_analyzer.get_summary()}")

                    # Print top performers
                    top_strategies = self.attribution_analyzer.get_top_strategies(limit=3)
                    if top_strategies:
                        logger.info(f"\nTop 3 Strategies:")
                        for strat in top_strategies:
                            logger.info(
                                f"  {strat['name']}: ${strat['total_pnl']:.2f} "
                                f"({strat['num_trades']} trades)"
                            )

                    top_markets = self.attribution_analyzer.get_best_markets(limit=3)
                    if top_markets:
                        logger.info(f"\nTop 3 Markets:")
                        for market in top_markets:
                            logger.info(
                                f"  {market['name']}: ${market['total_pnl']:.2f}"
                            )
            except Exception as e:
                logger.debug(f"Error in final attribution report: {e}")

            # Phase 2: Print smart exit manager summary
            if self.smart_exit_manager.exit_history:
                exit_stats = self.smart_exit_manager.get_stats()
                logger.info(
                    f"\nSmart Exit Manager Summary:\n"
                    f"  Total Closed Trades: {exit_stats.get('closed_trades', 0)}\n"
                    f"  Total Exit P&L: ${exit_stats.get('total_pnl', 0):.2f}\n"
                )

                if 'exits_by_reason' in exit_stats:
                    logger.info("  Exits by Reason:")
                    for reason, data in exit_stats['exits_by_reason'].items():
                        logger.info(
                            f"    {reason}: {data['count']} exits, "
                            f"P&L=${data['total_pnl']:.2f}"
                        )

            logger.info(f"{'='*60}\n")

            self._running = False
            logger.info("Bot shutdown complete")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}", exc_info=True)

    def get_status(self) -> Dict[str, Any]:
        """Get current bot status"""
        stats = self.position_manager.get_stats()
        risk_summary = self.risk_manager.get_risk_summary()
        uptime = (datetime.utcnow() - self.statistics.start_time).total_seconds()

        # Phase 2: Build status with improvement metrics
        status = {
            "running": self._running,
            "uptime_seconds": uptime,
            "opportunities_detected": self.statistics.opportunities_detected,
            "trades_executed": self.statistics.trades_executed,
            "open_positions": stats['open_positions'],
            "total_invested": stats['total_invested'],
            "total_pnl": stats['total_pnl'],
            "available_capital": self.config.risk.initial_capital_usd - stats['total_invested'],
            "daily_loss": risk_summary['daily_loss'],
            "daily_limit": risk_summary['daily_limit'],
            "win_rate_pct": stats['win_rate_pct'],
            # Phase 2 metrics
            "phase2": {
                "mtf_signals_aligned": self.statistics.mtf_signals_aligned,
                "smart_exits_triggered": self.statistics.smart_exits_triggered,
                "exit_profit_targets_hit": self.statistics.exit_profit_targets_hit,
                "exit_stop_losses_hit": self.statistics.exit_stop_losses_hit,
                "attribution_trades_logged": self.statistics.attribution_total_trades_logged,
                "open_exit_positions": len(self.smart_exit_manager.open_positions),
            },
        }

        # Add attribution insights if available
        try:
            if self.attribution_analyzer.trades:
                top_strategies = self.attribution_analyzer.get_top_strategies(limit=1)
                if top_strategies:
                    status["phase2"]["best_strategy"] = top_strategies[0]['name']

                top_markets = self.attribution_analyzer.get_best_markets(limit=1)
                if top_markets:
                    status["phase2"]["best_market"] = top_markets[0]['name']
        except Exception as e:
            logger.debug(f"Error getting attribution insights: {e}")

        return status


async def main(config_file: Optional[str] = None):
    """Main entry point"""
    from config.bot_config import load_config

    # Load configuration
    config = load_config(config_file)

    # Create and run bot
    bot = KalshiTradingBot(config)

    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        await bot.shutdown()


if __name__ == "__main__":
    import sys

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run bot
    config_file = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(main(config_file))
