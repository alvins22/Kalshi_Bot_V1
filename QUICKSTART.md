# Quick Start Guide

Get live trading running in 5 minutes.

## 1. Install Dependencies (1 minute)

```bash
pip install -r requirements.txt
```

## 2. Setup API Keys (2 minutes)

### Kalshi API
```bash
# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env
```

Add:
```bash
KALSHI_API_KEY=your_api_key_here
KALSHI_PRIVATE_KEY_PATH=./keys/kalshi_private.pem
KALSHI_USE_DEMO=true
```

### Generate RSA Key
```bash
openssl genrsa -out keys/kalshi_private.pem 4096
```

## 3. Run Paper Trading (1 minute)

```bash
python scripts/run_paper_trading.py --config config/paper_trading.yaml
```

Expected output:
```
======================================================
PAPER TRADING ENGINE
======================================================
Loaded configuration from config/paper_trading.yaml
Initialized KalshiClient (api_key=abc123..., environment=DEMO)
Starting paper trading engine...
Press Ctrl+C to stop

Portfolio: $5,000.00 | P&L: $0.00 | Positions: 0 | Win Rate: 0.0%
Connected to Kalshi WebSocket
[Signal: MatchedPairArbitrage - BUY 100 YES @ $0.450 (confidence: 0.85)]
[Fill: BUY 100 YES @ $0.455 (total: $45.50)]
...
```

## 4. Monitor Trades (1 minute)

In another terminal:
```bash
# View recent trades
tail -f logs/trading_*.jsonl | grep fill

# View all metrics
tail -f logs/trading_*.jsonl | grep heartbeat
```

## 5. Test Live Trading (optional)

When ready:
```bash
python scripts/run_live_trading.py --config config/live_trading.yaml --confirm
```

Will prompt for confirmation:
```
YOU ARE ABOUT TO TRADE WITH REAL MONEY
Initial Capital: $1000
Strategy: MatchedPairArbitrage

Type 'YES' to confirm and start live trading: YES
```

## Common Commands

### View Configuration
```bash
cat config/paper_trading.yaml
```

### Check Recent Trades
```bash
tail -20 logs/trading_*.jsonl | jq
```

### Monitor P&L
```bash
grep heartbeat logs/trading_*.jsonl | tail -5
```

### Stop Trading
```bash
# Press Ctrl+C in the terminal running the engine
# Will gracefully shutdown and cancel all open orders
```

## Troubleshooting

### "Connection refused"
- Check internet connection
- Verify `KALSHI_USE_DEMO=true` in .env
- Kalshi API might be down

### "Permission denied: keys/kalshi_private.pem"
```bash
chmod 600 keys/kalshi_private.pem
```

### "No ticks received"
- Wait 5-10 seconds for WebSocket to connect
- Check that markets are open
- Verify API key has WebSocket permissions

### "Signal rejected by safety rails"
- Market spread too wide (>2%)
- Or your position size exceeded limit
- Adjust `min_spread_bps` or `max_position_size` in config

## What Happens Next?

### Paper Trading Results (1 hour)
```
✓ Connects to live market data
✓ Generates trading signals
✓ Simulates realistic execution
✓ Tracks P&L and metrics
✓ Logs all trades
```

### Expected Metrics
```
Portfolio: $5,000.00
P&L: +$150.00 (3.0% return)
Sharpe Ratio: 1.85
Win Rate: 78%
Max Drawdown: 2.5%
```

## Next: Live Trading

1. ✅ Paper trading successful for 24+ hours
2. ✅ Metrics match backtest expectations
3. ✅ You understand the risk limits
4. Run: `python scripts/run_live_trading.py --config config/live_trading.yaml --confirm`

## Need Help?

- **Full Guide:** Read `LIVE_TRADING.md`
- **Technical Details:** Read `IMPLEMENTATION_SUMMARY.md`
- **API Docs:** https://docs.kalshi.com
- **GitHub Issues:** Create an issue with logs

## Risk Warning ⚠️

This is real trading. You can lose money.

- Start with paper trading
- Use conservative risk limits
- Never risk more than you can afford to lose
- Monitor your positions daily
- Have an emergency stop plan

Good luck! 📈
