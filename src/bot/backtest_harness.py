"""
Backtesting harness for integration with external backtesting engines

This module provides a simple interface for backtesting the bot with
historical Kalshi and Polymarket data from any source.

Example usage:
```python
from src.bot.backtest_harness import BacktestHarness
import pandas as pd

# Load historical data (Kalshi or Polymarket format)
data = pd.read_csv('historical_data.csv')

# Create harness
harness = BacktestHarness()

# Run backtest
results = harness.run_backtest(
    data=data,
    initial_capital=100000,
    start_date='2024-01-01',
    end_date='2024-12-31'
)

# Get results
print(f"Total Return: {results['total_return']:.2%}")
print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {results['max_drawdown']:.2%}")
```
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.bot.bot_interface import PredictionMarketBot, BotConfig
from src.data.models import MarketTick
from src.utils.metrics_tracker import MetricsTracker

logger = logging.getLogger(__name__)


class BacktestHarness:
    """
    Backtesting harness for prediction market bot

    Accepts historical data in any format with required OHLCV columns:
    - timestamp: datetime
    - market_id: str
    - yes_bid, yes_ask, no_bid, no_ask: float
    - volume_24h: float (optional)
    """

    def __init__(self, config: BotConfig = None):
        """Initialize backtesting harness"""
        self.config = config or BotConfig()
        self.bot = PredictionMarketBot(config=self.config)
        self.results = {
            'trades': [],
            'equity_curve': [],
            'timestamps': [],
            'signals': [],
        }

    def run_backtest(
        self,
        data: pd.DataFrame,
        initial_capital: float = 100000,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        resample_period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run backtest on historical data

        Args:
            data: DataFrame with OHLCV data
                Required columns: timestamp, market_id, yes_bid, yes_ask, no_bid, no_ask
                Optional columns: volume_24h, last_price
            initial_capital: Starting capital
            start_date: Start date filter (YYYY-MM-DD)
            end_date: End date filter (YYYY-MM-DD)
            resample_period: Resample data to period (e.g., '1min', '5min', '1h')

        Returns:
            Dict with backtest results and metrics
        """
        # Reset bot with initial capital
        self.bot.config.initial_capital = initial_capital
        self.bot = PredictionMarketBot(config=self.bot.config)

        # Validate data
        data = self._validate_and_prepare_data(data)

        # Filter by date range
        if start_date:
            data = data[data['timestamp'] >= pd.to_datetime(start_date)]
        if end_date:
            data = data[data['timestamp'] <= pd.to_datetime(end_date)]

        # Resample if requested
        if resample_period:
            data = self._resample_data(data, resample_period)

        logger.info(f"Running backtest on {len(data)} ticks from {data['timestamp'].min()} to {data['timestamp'].max()}")
        logger.info(f"Initial capital: ${initial_capital:,.0f}")

        # Process each market tick
        for idx, row in data.iterrows():
            if idx % 100 == 0:
                progress = int((idx / len(data)) * 100)
                logger.info(f"Progress: {progress}% ({idx}/{len(data)} ticks)")

            # Create market tick
            tick = self._row_to_tick(row)

            # Process tick and generate signals
            signals = self.bot.process_market_tick(tick)

            # Execute signals
            for signal in signals:
                fills = self.bot.execute_signal(signal)
                if fills:
                    self.results['signals'].append({
                        'timestamp': tick.timestamp,
                        'signal': signal,
                        'fills': fills,
                    })

            # Track equity curve
            self.results['timestamps'].append(tick.timestamp)
            self.results['equity_curve'].append(self.bot.portfolio.get_total_value())

        logger.info("Backtest completed")

        # Calculate metrics
        metrics = self._calculate_metrics()

        return metrics

    def _validate_and_prepare_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Validate and prepare data for backtesting"""
        required_columns = ['timestamp', 'market_id', 'yes_bid', 'yes_ask', 'no_bid', 'no_ask']

        # Check required columns
        missing = [col for col in required_columns if col not in data.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Convert timestamp to datetime
        data = data.copy()
        data['timestamp'] = pd.to_datetime(data['timestamp'])

        # Fill optional columns
        if 'volume_24h' not in data.columns:
            data['volume_24h'] = 1000
        if 'last_price' not in data.columns:
            data['last_price'] = (data['yes_bid'] + data['yes_ask']) / 2

        # Sort by timestamp
        data = data.sort_values('timestamp')

        return data

    def _row_to_tick(self, row: pd.Series) -> MarketTick:
        """Convert DataFrame row to MarketTick"""
        return MarketTick(
            timestamp=row['timestamp'],
            market_id=row['market_id'],
            exchange=row.get('exchange', 'kalshi'),
            yes_bid=float(row['yes_bid']),
            yes_ask=float(row['yes_ask']),
            no_bid=float(row['no_bid']),
            no_ask=float(row['no_ask']),
            volume_24h=int(row.get('volume_24h', 1000)),
            last_price=float(row.get('last_price', 0.5)),
        )

    def _resample_data(self, data: pd.DataFrame, period: str) -> pd.DataFrame:
        """Resample data to specified period (OHLCV)"""
        grouped = data.groupby('market_id')

        resampled_frames = []
        for market_id, group in grouped:
            group = group.set_index('timestamp')
            group = group.resample(period).agg({
                'yes_bid': 'first',
                'yes_ask': 'last',
                'no_bid': 'first',
                'no_ask': 'last',
                'volume_24h': 'sum',
                'last_price': 'last',
            })
            group['market_id'] = market_id
            resampled_frames.append(group)

        result = pd.concat(resampled_frames).reset_index()
        return result.sort_values('timestamp')

    def _calculate_metrics(self) -> Dict[str, Any]:
        """Calculate backtest metrics"""
        equity = np.array(self.results['equity_curve'])
        timestamps = np.array(self.results['timestamps'])

        if len(equity) < 2:
            return {'error': 'Insufficient data for metrics'}

        # Basic metrics
        initial_capital = self.bot.config.initial_capital
        final_value = equity[-1]
        total_return = (final_value - initial_capital) / initial_capital

        # Drawdown metrics
        cummax = np.maximum.accumulate(equity)
        drawdown = (equity - cummax) / cummax
        max_drawdown = np.min(drawdown)

        # Return metrics
        returns = np.diff(equity) / equity[:-1]
        annualized_return = np.mean(returns) * 252  # Annualized assuming daily data

        # Risk metrics
        volatility = np.std(returns) * np.sqrt(252)  # Annualized
        sharpe_ratio = annualized_return / volatility if volatility > 0 else 0

        # Downside volatility (Sortino)
        downside_returns = returns[returns < 0]
        downside_volatility = np.std(downside_returns) * np.sqrt(252) if len(downside_returns) > 0 else 0
        sortino_ratio = annualized_return / downside_volatility if downside_volatility > 0 else 0

        # Win rate
        winning_trades = sum(1 for r in returns if r > 0)
        win_rate = winning_trades / len(returns) if len(returns) > 0 else 0

        # Profit factor
        gains = sum(r for r in returns if r > 0)
        losses = abs(sum(r for r in returns if r < 0))
        profit_factor = gains / losses if losses > 0 else 0

        # Trade count
        num_trades = len(self.results['signals'])

        return {
            'initial_capital': initial_capital,
            'final_value': final_value,
            'total_return': total_return,
            'annualized_return': annualized_return,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'max_drawdown': max_drawdown,
            'volatility': volatility,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'num_trades': num_trades,
            'num_ticks': len(equity),
            'date_range': {
                'start': timestamps[0],
                'end': timestamps[-1],
            },
        }

    def get_equity_curve(self) -> tuple:
        """Get equity curve (timestamps, values)"""
        return (
            np.array(self.results['timestamps']),
            np.array(self.results['equity_curve']),
        )

    def get_signals(self) -> List[Dict]:
        """Get all signals generated during backtest"""
        return self.results['signals']

    def export_results(self, filepath: str):
        """Export backtest results to CSV"""
        df = pd.DataFrame({
            'timestamp': self.results['timestamps'],
            'equity': self.results['equity_curve'],
        })
        df.to_csv(filepath, index=False)
        logger.info(f"Results exported to {filepath}")
