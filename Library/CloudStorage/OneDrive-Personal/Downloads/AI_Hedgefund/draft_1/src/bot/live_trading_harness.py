"""
Live trading harness for real-time prediction market trading

This module provides the interface for running the bot in live trading mode
against Kalshi and Polymarket APIs.

Example usage:
```python
from src.bot.live_trading_harness import LiveTradingHarness
from src.exchanges.kalshi import KalshiClient

# Initialize clients
kalshi_client = KalshiClient(api_key='your_api_key')

# Create harness
harness = LiveTradingHarness(kalshi_client)

# Start trading
harness.start()
```
"""

import asyncio
import logging
from typing import Optional, Dict, Any

from src.bot.bot_interface import PredictionMarketBot, BotConfig
from src.data.models import MarketTick

logger = logging.getLogger(__name__)


class LiveTradingHarness:
    """
    Live trading harness for prediction market bot

    Connects to Kalshi and Polymarket APIs and executes trades in real-time.
    """

    def __init__(
        self,
        kalshi_client: Optional[Any] = None,
        polymarket_client: Optional[Any] = None,
        config: BotConfig = None,
    ):
        """
        Initialize live trading harness

        Args:
            kalshi_client: KalshiClient instance
            polymarket_client: PolymMarketClient instance
            config: Bot configuration
        """
        self.kalshi_client = kalshi_client
        self.polymarket_client = polymarket_client
        self.config = config or BotConfig()

        # Initialize bot
        self.bot = PredictionMarketBot(config=self.config)

        # Trading state
        self.is_running = False
        self.market_subscriptions: Dict[str, str] = {}  # market_id -> exchange

        logger.info("Initialized LiveTradingHarness")

    async def start(self):
        """Start live trading"""
        if self.is_running:
            logger.warning("Live trading already running")
            return

        self.is_running = True
        logger.info("Starting live trading")

        # Reset daily limits at start of trading
        self.bot.reset_daily_limits()

        # Connect to exchanges
        tasks = []

        if self.kalshi_client:
            tasks.append(self._run_kalshi_trading())

        if self.polymarket_client:
            tasks.append(self._run_polymarket_trading())

        if not tasks:
            logger.error("No exchange clients available")
            return

        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Error in live trading: {e}", exc_info=True)
            self.is_running = False

    async def stop(self):
        """Stop live trading"""
        self.is_running = False
        logger.info("Stopping live trading")

    async def _run_kalshi_trading(self):
        """Trading loop for Kalshi"""
        logger.info("Starting Kalshi trading loop")

        try:
            # Get available markets
            markets = await self._fetch_kalshi_markets()
            market_ids = [m['market_id'] for m in markets[:10]]  # Top 10 markets

            logger.info(f"Subscribing to {len(market_ids)} Kalshi markets")

            # Subscribe to WebSocket
            async for tick in self._kalshi_websocket_stream(market_ids):
                if not self.is_running:
                    break

                # Process tick
                await self._process_tick(tick, 'kalshi')

        except Exception as e:
            logger.error(f"Kalshi trading error: {e}", exc_info=True)

    async def _run_polymarket_trading(self):
        """Trading loop for Polymarket"""
        logger.info("Starting Polymarket trading loop")

        try:
            # Get available markets
            markets = await self._fetch_polymarket_markets()
            market_ids = [m['id'] for m in markets[:10]]  # Top 10 markets

            logger.info(f"Subscribing to {len(market_ids)} Polymarket markets")

            # Subscribe to WebSocket
            async for tick in self._polymarket_websocket_stream(market_ids):
                if not self.is_running:
                    break

                # Process tick
                await self._process_tick(tick, 'polymarket')

        except Exception as e:
            logger.error(f"Polymarket trading error: {e}", exc_info=True)

    async def _process_tick(self, tick: MarketTick, exchange: str):
        """Process a market tick and execute trading logic"""
        try:
            # Process tick through bot
            signals = self.bot.process_market_tick(tick)

            # Execute signals
            for signal in signals:
                await self._execute_signal(signal, exchange)

        except Exception as e:
            logger.error(f"Error processing tick: {e}")

    async def _execute_signal(self, signal: Any, exchange: str):
        """Execute a trading signal on the specified exchange"""
        try:
            if not self.bot.is_trading_allowed:
                logger.warning(f"Trading halted: {self.bot.halt_reason}")
                return

            # Get market state for execution context
            if signal.market_id not in self.bot.market_states:
                logger.warning(f"No market state for {signal.market_id}")
                return

            market_state = self.bot.market_states[signal.market_id]

            # Execute on appropriate exchange
            if exchange == 'kalshi' and self.kalshi_client:
                await self._execute_kalshi_order(signal, market_state)
            elif exchange == 'polymarket' and self.polymarket_client:
                await self._execute_polymarket_order(signal, market_state)

        except Exception as e:
            logger.error(f"Error executing signal: {e}")

    async def _execute_kalshi_order(self, signal: Any, market_state: Any):
        """Execute order on Kalshi"""
        try:
            # Convert signal to Kalshi order
            order_type = "BUY" if signal.direction.name == "BUY" else "SELL"
            yes_no = "YES" if signal.outcome.name == "YES" else "NO"

            logger.info(
                f"Kalshi order: {order_type} {signal.contracts} {yes_no} "
                f"at {market_state.yes_mid:.3f} ({signal.market_id})"
            )

            # Execute order
            result = await self.kalshi_client.place_order(
                market_id=signal.market_id,
                side=order_type,
                contract=yes_no,
                quantity=signal.contracts,
                price=market_state.yes_mid,
            )

            logger.info(f"Order executed: {result}")

            # Update bot portfolio
            self.bot.execute_signal(signal)

        except Exception as e:
            logger.error(f"Kalshi order execution error: {e}")

    async def _execute_polymarket_order(self, signal: Any, market_state: Any):
        """Execute order on Polymarket"""
        try:
            # Convert signal to Polymarket order
            direction = "BUY" if signal.direction.name == "BUY" else "SELL"
            outcome = signal.outcome.name

            logger.info(
                f"Polymarket order: {direction} {signal.contracts} {outcome} "
                f"at {market_state.yes_mid:.3f} ({signal.market_id})"
            )

            # Execute order
            result = await self.polymarket_client.place_order(
                market_id=signal.market_id,
                direction=direction,
                outcome=outcome,
                quantity=signal.contracts,
                price=market_state.yes_mid,
            )

            logger.info(f"Order executed: {result}")

            # Update bot portfolio
            self.bot.execute_signal(signal)

        except Exception as e:
            logger.error(f"Polymarket order execution error: {e}")

    async def _fetch_kalshi_markets(self):
        """Fetch available markets from Kalshi"""
        if not self.kalshi_client:
            return []

        try:
            markets = await self.kalshi_client.get_markets(limit=100)
            logger.info(f"Fetched {len(markets)} Kalshi markets")
            return markets
        except Exception as e:
            logger.error(f"Error fetching Kalshi markets: {e}")
            return []

    async def _fetch_polymarket_markets(self):
        """Fetch available markets from Polymarket"""
        if not self.polymarket_client:
            return []

        try:
            markets = await self.polymarket_client.get_markets(limit=100)
            logger.info(f"Fetched {len(markets)} Polymarket markets")
            return markets
        except Exception as e:
            logger.error(f"Error fetching Polymarket markets: {e}")
            return []

    async def _kalshi_websocket_stream(self, market_ids: list):
        """Stream Kalshi market data via WebSocket"""
        if not self.kalshi_client:
            return

        try:
            async for tick in self.kalshi_client.subscribe_ticker(market_ids):
                yield tick
        except Exception as e:
            logger.error(f"Kalshi WebSocket error: {e}")

    async def _polymarket_websocket_stream(self, market_ids: list):
        """Stream Polymarket market data via WebSocket"""
        if not self.polymarket_client:
            return

        try:
            async for tick in self.polymarket_client.subscribe_ticker(market_ids):
                yield tick
        except Exception as e:
            logger.error(f"Polymarket WebSocket error: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get current live trading status"""
        return {
            'is_running': self.is_running,
            'bot_status': self.bot.get_status(),
        }
