# Live Trading Implementation Guide

This document covers the live trading infrastructure built on top of the prediction market backtesting framework.

## Overview

The system has been extended from backtesting-only to a production-ready live trading system with three phases:

1. **Phase 1: Paper Trading** (3-5 days) - Test with live market data, simulated execution
2. **Phase 2: Kalshi Live Trading** (2-3 days) - Real money on Kalshi with safety rails
3. **Phase 3: Multi-Exchange** (2-3 days) - Cross-exchange arbitrage (Kalshi + Polymarket)

## Architecture

### Core Components

```
Market Data → MarketState → Strategy → Signal → Safety Rails → Order Manager → Execution
     ↓            ↓          ↓         ↓          ↓             ↓              ↓
  WebSocket   MarketState  Strategy  Signal    SafetyRails   OrderManager   Fill
  REST API    (bid/ask)    Signals   Valid?    Checks        Lifecycle      Process
```

### Reusable Code (90%)
- Strategy classes (MatchedPairArbitrage, DirectionalMomentum, MarketMaking)
- Risk management (KellyCriterion, PositionManager)
- Data models (Signal, Fill, Position, Portfolio)
- ExecutionSimulator (for paper trading)

### New Infrastructure (10%)
- Kalshi REST API client (`src/exchanges/kalshi/kalshi_client.py`)
- Kalshi WebSocket client (`src/exchanges/kalshi/kalshi_websocket.py`)
- Order management system (`src/trading/order_manager.py`)
- Safety rails (`src/trading/safety_rails.py`)
- Live trading engine (`src/trading/live_trading_engine.py`)
- Paper trading engine (`src/trading/paper_trading_engine.py`)
- Polymarket client (`src/exchanges/polymarket/polymarket_client.py`)
- Multi-exchange engine (`src/trading/multi_exchange_engine.py`)

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Get API Credentials

**Kalshi:**
1. Create account at https://www.kalshi.com
2. Get API key from settings
3. Generate RSA private key:
   ```bash
   openssl genrsa -out keys/kalshi_private.pem 4096
   ```
4. Register public key with Kalshi API

**Polymarket:**
1. Create account at https://polymarket.com
2. Export private key from wallet
3. Ensure testnet MATIC and USDC for testing

### 3. Configuration

Create `.env` file:
```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```bash
KALSHI_API_KEY=your_api_key
KALSHI_PRIVATE_KEY_PATH=./keys/kalshi_private.pem
KALSHI_USE_DEMO=true

POLYMARKET_PRIVATE_KEY=your_private_key
POLYMARKET_CHAIN_ID=137
```

## Phase 1: Paper Trading

### Run Paper Trading

```bash
python scripts/run_paper_trading.py --config config/paper_trading.yaml
```

### What Happens

1. Connects to Kalshi WebSocket for live market data
2. Generates signals using MatchedPairArbitrage strategy
3. Simulates order execution with realistic slippage
4. Updates portfolio and metrics every 60 seconds
5. Logs all trades to `logs/trading_YYYYMMDD.jsonl`

### Verification

After 1 hour:
- Check logs: `logs/trading_*.jsonl`
- Verify signal generation frequency matches backtest
- Compare P&L to backtest (should be within 10-20%)
- Test Ctrl+C for graceful shutdown

### Configuration

**File:** `config/paper_trading.yaml`

```yaml
mode: paper
exchange: kalshi
initial_capital: 5000
strategy_name: MatchedPairArbitrage
strategy_params:
  min_spread_bps: 200  # Only take trades with 2%+ edge
  max_position_size: 1000

risk_limits:
  max_position_size: 1000       # Max $1K per position
  max_daily_loss: 250           # Stop if lose $250/day (5%)
  max_drawdown: 1000            # Stop if down $1K from peak (20%)
  max_open_positions: 5
  min_spread_bps: 200
  emergency_stop_on_breach: true
```

## Phase 2: Live Trading

### Pre-Flight Checklist

Before going live:
- [ ] Backtests show positive Sharpe ratio (>1.0)
- [ ] Paper trading profitable for 3+ consecutive days
- [ ] All error scenarios tested (WebSocket drops, API errors)
- [ ] Emergency stop tested manually
- [ ] Starting capital deposited ($1K-$5K)
- [ ] Risk limits configured
- [ ] Kill switch working

### Run Kalshi Live Trading

```bash
python scripts/run_live_trading.py --config config/live_trading.yaml --confirm
```

### Safety Features

1. **Order Manager** - Track order lifecycle (PENDING → FILLED/CANCELLED)
2. **Safety Rails** - Checks before every order:
   - Position size limit
   - Daily loss limit
   - Drawdown limit
   - Price sanity check (±5% from market)
   - Market liquidity check
   - Open position count limit

3. **Emergency Stop** - Automatic triggers:
   - Daily loss exceeds limit → stop trading
   - Drawdown exceeds limit → stop trading
   - Critical error → graceful shutdown

4. **Monitoring** - Real-time alerts:
   - Order fills
   - Risk breaches
   - WebSocket disconnections
   - Critical errors
   - Daily P&L summary

### Configuration

**File:** `config/live_trading.yaml`

```yaml
mode: live
exchange: kalshi
initial_capital: 1000  # Start conservative!

risk_limits:
  max_position_size: 500        # 50% of capital
  max_daily_loss: 100           # 10% of capital
  max_drawdown: 200             # 20% of capital
  max_open_positions: 3
  emergency_stop_on_breach: true
```

### Real-Money Trading Flow

1. User confirmation required: "Type 'YES' to confirm"
2. Verify balance ≥ initial capital
3. Reconcile existing positions
4. Subscribe to fills via WebSocket
5. Start monitoring loops:
   - Signal generation every 1 second
   - Order submission every 0.5 seconds
   - Fill reconciliation every 60 seconds
   - Metrics/heartbeat every 60 seconds
6. Log every trade to JSON file
7. Stop with Ctrl+C (cancels all orders, exits gracefully)

## Phase 3: Multi-Exchange Trading

### Run Multi-Exchange Engine

```bash
python scripts/run_multi_exchange.py --config config/multi_exchange.yaml --mode paper
```

### Cross-Exchange Arbitrage

The engine monitors for matched pair arbitrage across Kalshi and Polymarket:

**Scenario 1: Kalshi Mispricing**
```
Kalshi: YES @ 0.45, NO @ 0.45 (total: 0.90)
→ Profit: 0.10 (10%)

Strategy: Buy YES + NO on Kalshi, hold until event resolves
```

**Scenario 2: Polymarket Mispricing**
```
Polymarket: YES @ 0.40, NO @ 0.40 (total: 0.80)
→ Profit: 0.20 (20%)

Strategy: Buy YES + NO on Polymarket, hold until event resolves
```

**Scenario 3: Asymmetric Pricing**
```
Kalshi: NO @ 0.35
Polymarket: YES @ 0.60
Total cost: 0.95 → Profit: 0.05 (5%)

Strategy: Buy NO on Kalshi, buy YES on Polymarket
```

### Configuration

**File:** `config/multi_exchange.yaml`

```yaml
mode: paper
exchange: multi
initial_capital: 2000

strategy_name: MatchedPairArbitrage
strategy_params:
  min_spread_bps: 100  # Lower threshold for multi-exchange

risk_limits:
  max_position_size: 500
  max_daily_loss: 200
  max_drawdown: 400
  max_open_positions: 10
  min_spread_bps: 100
```

## File Structure

```
draft_1/
├── config/
│   ├── paper_trading.yaml      # Paper trading config
│   ├── live_trading.yaml       # Live trading config (conservative)
│   └── multi_exchange.yaml     # Multi-exchange config
├── keys/
│   ├── kalshi_private.pem      # PRIVATE - not in git
│   └── .gitkeep
├── logs/
│   ├── trading_20240407.jsonl  # Structured logs
│   └── .gitkeep
├── src/
│   ├── exchanges/
│   │   ├── kalshi/
│   │   │   ├── kalshi_client.py        # REST API
│   │   │   ├── kalshi_websocket.py     # WebSocket
│   │   │   └── models.py               # Data models
│   │   └── polymarket/
│   │       ├── polymarket_client.py
│   │       └── models.py
│   ├── trading/
│   │   ├── paper_trading_engine.py     # Paper trading
│   │   ├── live_trading_engine.py      # Live trading
│   │   ├── multi_exchange_engine.py    # Multi-exchange
│   │   ├── order_manager.py            # Order lifecycle
│   │   ├── safety_rails.py             # Risk checks
│   │   └── trading_config.py           # Configuration
│   ├── utils/
│   │   ├── trading_logger.py           # Structured logging
│   │   ├── metrics_tracker.py          # Real-time metrics
│   │   ├── alert_manager.py            # Alerts/notifications
│   │   └── config_loader.py            # Config loading
│   ├── strategies/
│   ├── risk/
│   ├── backtesting/
│   └── data/
├── scripts/
│   ├── run_paper_trading.py    # Entry point: paper trading
│   ├── run_live_trading.py     # Entry point: live trading
│   └── run_multi_exchange.py   # Entry point: multi-exchange
├── tests/
│   ├── integration/
│   │   ├── test_kalshi_client.py
│   │   ├── test_kalshi_websocket.py
│   │   └── test_paper_trading_engine.py
│   └── unit/
├── .env.example                # Environment template
├── .gitignore                  # Git ignore rules
├── requirements.txt            # Dependencies
└── LIVE_TRADING.md            # This file
```

## Monitoring & Debugging

### Real-Time Metrics

Check console output for:
```
Portfolio: $4,950.25 | P&L: $-49.75 | Positions: 2 | Win Rate: 75.0%
```

### JSON Logs

```bash
# View recent fills
tail -100 logs/trading_20240407.jsonl | grep '"event_type":"fill"'

# View all signals
grep '"event_type":"signal"' logs/trading_*.jsonl

# Check for errors
grep '"level":"ERROR"' logs/trading_*.jsonl
```

### Test WebSocket Connection

```python
import asyncio
from src.exchanges.kalshi import KalshiWebSocket
from src.data.models import MarketTick

async def test():
    ws = KalshiWebSocket(api_key="YOUR_KEY", is_demo=True)

    received_ticks = []

    def on_tick(tick: MarketTick):
        received_ticks.append(tick)
        print(f"Received: {tick.market_id} YES ${tick.yes_mid:.3f}")

    ws.set_on_tick(on_tick)

    if await ws.connect():
        await ws.subscribe_ticker(["MARKET_ID_1", "MARKET_ID_2"])
        await asyncio.sleep(10)
        await ws.disconnect()

        print(f"Received {len(received_ticks)} ticks")

asyncio.run(test())
```

## Common Issues

### 1. RSA Key Not Found

```
Failed to load private key: [Errno 2] No such file or directory
```

**Solution:**
```bash
openssl genrsa -out keys/kalshi_private.pem 4096
# Register public key with Kalshi
```

### 2. WebSocket Connection Refused

```
WebSocket connection failed: Connection refused
```

**Solution:**
- Verify `KALSHI_USE_DEMO=true` in `.env` for testing
- Check internet connection
- Kalshi API might be down - check https://status.kalshi.com

### 3. Order Rejected by Safety Rails

```
Signal rejected by safety rails: Position size exceeds limit
```

**Solution:**
- Adjust `max_position_size` in config
- Or reduce `contracts` in signal

### 4. No Fills Received

```
Generated 10 signals but no fills
```

**Possible causes:**
- Market is illiquid (bid-ask spread > 2%)
- Insufficient balance for order
- Order price outside acceptable range
- Market closed

## Performance Expectations

### Matched Pair Arbitrage

- **Expected Return:** 15-25% annually
- **Max Drawdown:** 5-10%
- **Trade Frequency:** 10-20 trades/day
- **Win Rate:** 85-95%

### Reality vs Backtest

Live trading typically underperforms backtests by 20-30% due to:
- Real slippage (1-2% on limit orders)
- Network latency (50-100ms)
- Fees (0.1-0.5% per trade on Kalshi)
- Partial fills
- Market impact on large orders

**Conservative Estimate:** 50-70% of backtest returns

## Risk Management Best Practices

### Daily Loss Limit

Your portfolio can lose at most 5-10% per day before emergency stop triggers.

Example with $5K capital:
- Max daily loss: $250 (5%)
- Stop trading if down $250 in a day

### Max Drawdown

Cap your losses from peak capital.

Example:
- Peak capital: $5,500
- Max drawdown: $1,000 (20%)
- Stop trading if down to $4,500

### Position Sizing

Follow Kelly Criterion:
```
Position Size = (Win Rate × Avg Win - (1 - Win Rate) × Avg Loss) / Avg Win
```

For 80% win rate, 2% avg win, 5% avg loss:
```
Position Size = (0.80 × 0.02 - 0.20 × 0.05) / 0.02 = 30% of capital
```

## Deployment

### On VPS/Cloud Server

```bash
# SSH into server
ssh user@server.ip

# Clone repository
git clone <repo> draft_1
cd draft_1

# Install dependencies
pip install -r requirements.txt

# Configure environment
nano .env

# Run in screen/tmux session
tmux new-session -d -s trading "python scripts/run_live_trading.py --config config/live_trading.yaml --confirm"

# Monitor
tmux attach-session -t trading
```

### Keep-Alive Script

```bash
#!/bin/bash
# restart_trading.sh

while true; do
    python scripts/run_live_trading.py \
        --config config/live_trading.yaml \
        --confirm

    # Restart if crashed
    sleep 5
done
```

## Support & Resources

### Kalshi API
- Docs: https://docs.kalshi.com
- API Guide: https://pm.wiki/learn/kalshi-api
- Status: https://status.kalshi.com

### Polymarket
- Docs: https://docs.polymarket.com
- py-clob-client: https://github.com/Polymarket/py-clob-client

### Prediction Markets
- Learning: https://kalshi.com/learn
- Markets: https://kalshi.com/markets

## Next Steps

1. **Complete Paper Trading**: Run for 24+ hours, verify metrics match backtest
2. **Deploy Live (Small Capital)**: Start with $1K, focus on stability
3. **Monitor Daily**: Check logs every morning, adjust risk limits if needed
4. **Scale Gradually**: Increase capital 20-30% per week if profitable
5. **Multi-Exchange**: Add Polymarket after Kalshi stable

## Disclaimer

Trading prediction markets involves real financial risk. Past performance does not guarantee future results. This code is provided for educational purposes only. Use at your own risk with capital you can afford to lose.
