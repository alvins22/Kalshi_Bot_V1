"""
Unified bot interface for prediction market trading

This module provides a complete bot implementation that combines:
- All trading strategies (arbitrage, momentum, mean reversion, etc.)
- All risk management modules (volatility sizing, dynamic risk, drawdown control)
- Backtesting interface for historical analysis
- Live trading interface for real-time execution
"""

from .bot_interface import PredictionMarketBot, BotConfig
from .backtest_harness import BacktestHarness
from .live_trading_harness import LiveTradingHarness

__all__ = [
    'PredictionMarketBot',
    'BotConfig',
    'BacktestHarness',
    'LiveTradingHarness',
]
