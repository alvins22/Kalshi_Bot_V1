#!/usr/bin/env python3
"""
Example: Running backtest with the bot

This example shows how to use the bot with historical data for backtesting.
Compatible with your friend's backtesting engine - just pass historical data
in the required format.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from src.bot import BacktestHarness, BotConfig


def example_1_basic_backtest():
    """Example 1: Basic backtest with default configuration"""
    print("=" * 80)
    print("Example 1: Basic Backtest with Default Configuration")
    print("=" * 80)

    # Create bot configuration
    config = BotConfig(
        initial_capital=100000,
        log_dir="logs/backtest",
    )

    # Create backtesting harness
    harness = BacktestHarness(config=config)

    # Load historical data (in format: timestamp, market_id, yes_bid, yes_ask, no_bid, no_ask, volume_24h)
    # This is compatible with Kalshi and Polymarket data formats
    data = pd.read_csv("sample_historical_data.csv")

    print(f"Loaded {len(data)} ticks from {data['timestamp'].min()} to {data['timestamp'].max()}")

    # Run backtest
    results = harness.run_backtest(
        data=data,
        initial_capital=100000,
    )

    # Print results
    print_results(results)

    # Save equity curve
    harness.export_results("backtest_results.csv")


def example_2_custom_config():
    """Example 2: Backtest with custom risk configuration"""
    print("\n" + "=" * 80)
    print("Example 2: Backtest with Custom Risk Configuration")
    print("=" * 80)

    # Custom configuration for more aggressive trading
    config = BotConfig(
        initial_capital=100000,
        base_max_daily_loss_pct=0.03,  # Allow 3% daily loss
        base_max_position_size_pct=0.08,  # Allow 8% per position
        base_max_drawdown_pct=0.20,  # Allow 20% max drawdown
        target_risk_pct=0.025,  # Target 2.5% risk per trade
    )

    harness = BacktestHarness(config=config)
    data = pd.read_csv("sample_historical_data.csv")

    results = harness.run_backtest(data=data, initial_capital=100000)
    print_results(results)


def example_3_date_range():
    """Example 3: Backtest specific date range"""
    print("\n" + "=" * 80)
    print("Example 3: Backtest Specific Date Range")
    print("=" * 80)

    config = BotConfig(initial_capital=100000)
    harness = BacktestHarness(config=config)
    data = pd.read_csv("sample_historical_data.csv")

    # Backtest only Jan 2024
    results = harness.run_backtest(
        data=data,
        initial_capital=100000,
        start_date='2024-01-01',
        end_date='2024-01-31',
    )

    print_results(results)


def example_4_resampled_data():
    """Example 4: Backtest with resampled data"""
    print("\n" + "=" * 80)
    print("Example 4: Backtest with Resampled Data (1-minute bars)")
    print("=" * 80)

    config = BotConfig(initial_capital=100000)
    harness = BacktestHarness(config=config)
    data = pd.read_csv("sample_historical_data.csv")

    # Resample tick data to 1-minute OHLCV bars
    results = harness.run_backtest(
        data=data,
        initial_capital=100000,
        resample_period='1min',
    )

    print_results(results)


def example_5_from_kalshi_data():
    """Example 5: Backtest with Kalshi historical data"""
    print("\n" + "=" * 80)
    print("Example 5: Backtest with Kalshi Historical Data")
    print("=" * 80)

    # Load Kalshi data (CSV format with columns: timestamp, market_id, yes_bid, yes_ask, no_bid, no_ask, volume_24h)
    # This should match the format from your data provider
    data = pd.read_csv("kalshi_historical_ticks.csv")

    config = BotConfig(initial_capital=100000)
    harness = BacktestHarness(config=config)

    results = harness.run_backtest(
        data=data,
        initial_capital=100000,
    )

    print_results(results)

    # Visualize equity curve
    timestamps, equity = harness.get_equity_curve()
    print(f"\nEquity curve: {len(timestamps)} points")
    print(f"Starting value: ${equity[0]:,.0f}")
    print(f"Ending value: ${equity[-1]:,.0f}")


def example_6_polymarket_data():
    """Example 6: Backtest with Polymarket historical data"""
    print("\n" + "=" * 80)
    print("Example 6: Backtest with Polymarket Historical Data")
    print("=" * 80)

    # Load Polymarket data (CSV format with columns: timestamp, market_id, yes_bid, yes_ask, no_bid, no_ask, volume_24h)
    data = pd.read_csv("polymarket_historical_ticks.csv")

    config = BotConfig(initial_capital=100000)
    harness = BacktestHarness(config=config)

    results = harness.run_backtest(
        data=data,
        initial_capital=100000,
    )

    print_results(results)


def print_results(results):
    """Pretty print backtest results"""
    print("\n" + "=" * 80)
    print("BACKTEST RESULTS")
    print("=" * 80)

    if 'error' in results:
        print(f"Error: {results['error']}")
        return

    print(f"Initial Capital:      ${results['initial_capital']:>15,.2f}")
    print(f"Final Value:          ${results['final_value']:>15,.2f}")
    print(f"Total Return:         {results['total_return']:>15.2%}")
    print()
    print(f"Annualized Return:    {results['annualized_return']:>15.2%}")
    print(f"Annualized Volatility:{results['volatility']:>15.2%}")
    print(f"Sharpe Ratio:         {results['sharpe_ratio']:>15.2f}")
    print(f"Sortino Ratio:        {results['sortino_ratio']:>15.2f}")
    print()
    print(f"Max Drawdown:         {results['max_drawdown']:>15.2%}")
    print(f"Win Rate:             {results['win_rate']:>15.2%}")
    print(f"Profit Factor:        {results['profit_factor']:>15.2f}")
    print()
    print(f"Number of Trades:     {results['num_trades']:>15d}")
    print(f"Number of Ticks:      {results['num_ticks']:>15d}")
    print(f"Date Range:           {results['date_range']['start']} to {results['date_range']['end']}")
    print("=" * 80)


if __name__ == "__main__":
    """Run examples"""
    print("\nPrediction Market Bot - Backtesting Examples")
    print("=" * 80)
    print("\nThese examples show how to use the bot for backtesting with historical data.")
    print("Compatible with Kalshi, Polymarket, and custom data formats.")
    print()
    print("To run examples, make sure you have historical data files in the appropriate format:")
    print("  - sample_historical_data.csv (generic format)")
    print("  - kalshi_historical_ticks.csv (Kalshi format)")
    print("  - polymarket_historical_ticks.csv (Polymarket format)")
    print()
    print("Data format required:")
    print("  timestamp (datetime)")
    print("  market_id (str)")
    print("  yes_bid, yes_ask (float)")
    print("  no_bid, no_ask (float)")
    print("  volume_24h (float, optional)")
    print()

    # Run examples (comment out those without data)
    try:
        example_1_basic_backtest()
    except FileNotFoundError:
        print("Note: Example 1 requires 'sample_historical_data.csv'")

    try:
        example_2_custom_config()
    except FileNotFoundError:
        print("Note: Example 2 requires 'sample_historical_data.csv'")

    try:
        example_3_date_range()
    except FileNotFoundError:
        print("Note: Example 3 requires 'sample_historical_data.csv'")

    try:
        example_4_resampled_data()
    except FileNotFoundError:
        print("Note: Example 4 requires 'sample_historical_data.csv'")

    try:
        example_5_from_kalshi_data()
    except FileNotFoundError:
        print("Note: Example 5 requires 'kalshi_historical_ticks.csv'")

    try:
        example_6_polymarket_data()
    except FileNotFoundError:
        print("Note: Example 6 requires 'polymarket_historical_ticks.csv'")
