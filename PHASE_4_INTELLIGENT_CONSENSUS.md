# Phase 4: Intelligent Consensus Engine with Learning

## Problem Statement

The original consensus engine used **Winner-Take-All** conflict resolution:

```python
# Old approach: Just pick the side with higher average confidence
buy_conf = mean([s.confidence for s in buys])
sell_conf = mean([s.confidence for s in sells])
chosen_side = buys if buy_conf >= sell_conf else sells
```

**Issues:**
1. **Throws away 50% of information** when conflicts occur
2. **No historical learning** - doesn't use past accuracy to weight decisions
3. **No regime awareness** - same weight for all strategies regardless of market regime
4. **No uncertainty modeling** - treats close calls (50/50) same as clear majorities (75/25)
5. **Black box merging** - no tracking of which conflicts it resolved correctly

---

## Phase 4 Solution: Three Components

### 1. Conflict Tracking System

Every time 2+ strategies disagree, the system logs:

```python
@dataclass
class ConflictOutcome:
    timestamp: float
    market_id: str
    buy_agents: List[str]      # ["arbitrage", "momentum"]
    sell_agents: List[str]     # ["mean_reversion"]
    buy_avg_conf: float        # 0.825
    sell_avg_conf: float       # 0.72
    chosen_direction: Direction # BUY (chosen by algorithm)
    actual_outcome: Optional[bool] = None  # True if chosen was correct
    position_pnl: float = 0.0
```

After backtesting, we know:
- **When conflicts happen**: "arbitrage + momentum vs mean_reversion" pattern
- **Who was right**: Did BUY or SELL actually win?
- **What we earned/lost**: Track PnL from the chosen direction

**Example from backtesting:**
```
Conflict #1: 2v2 (arb+momentum vs mr+cross) → chose BUY → market went +2% → ✓
Conflict #2: 2v2 (arb+momentum vs mr+cross) → chose BUY → market went -1% → ✗
Conflict #3: 3v1 (arb+momentum+mr vs cross) → chose BUY → market went +3% → ✓

Insight: When it's 3v1, we're ~80% right. When it's 2v2, we're ~50/50.
```

### 2. Regime Detection

Markets have different regimes where different strategies win:

```python
class MarketRegime(Enum):
    TRENDING           # Momentum strategy dominates
    MEAN_REVERTING     # Mean reversion strategy dominates
    RANGE_BOUND        # Arbitrage strategy dominates
    HIGH_VOLATILITY    # Different strategy mix
    LOW_VOLATILITY     # Different strategy mix
```

**Detection Logic:**
```python
def detect_regime(prices, returns):
    trend_strength = slope_of_prices / mean_price      # -1 to +1
    reversion_score = -lag1_autocorrelation            # 0 to 1
    volatility = std(returns)

    if volatility > 0.15:
        return HIGH_VOLATILITY
    elif trend_strength > 0.3:
        return TRENDING
    elif reversion_score > 0.3:
        return MEAN_REVERTING
    else:
        return RANGE_BOUND
```

**Regime-Aware Weights:**
```python
regime_weights = {
    'enhanced_matched_pair': {
        MarketRegime.RANGE_BOUND: 0.8,    # Arb dominates in ranging markets
        MarketRegime.TRENDING: 0.2,
        MarketRegime.MEAN_REVERTING: 0.3,
    },
    'improved_momentum': {
        MarketRegime.TRENDING: 0.8,       # Momentum dominates in trends
        MarketRegime.RANGE_BOUND: 0.1,
        MarketRegime.MEAN_REVERTING: 0.2,
    },
    # ... etc
}
```

**Effect in Backtesting:**
- During downtrend: Momentum signals weighted 80% → Position sizing up
- During consolidation: Arbitrage signals weighted 80% → Position sizing up
- During mean-reverting period: Mean reversion signals weighted 80% → Position sizing up

### 3. Bayesian Fusion

Instead of averaging confidences, use proper Bayesian model:

```python
# Each strategy is a noisy signal with likelihood of being correct
# P(BUY correct | all signals) ∝ P(signals | BUY) × P(BUY prior)

buy_likelihood = 1.0
for agent in buy_signals:
    # Weight by regime relevance + historical accuracy
    weight = regime_weight[agent] * historical_accuracy[agent]
    # Product of weighted confidences
    buy_likelihood *= (confidence[agent] ** weight)

sell_likelihood = 1.0  # Same for sell side
for agent in sell_signals:
    weight = regime_weight[agent] * historical_accuracy[agent]
    sell_likelihood *= (confidence[agent] ** weight)

# Normalize to probability
p_buy = buy_likelihood / (buy_likelihood + sell_likelihood)
p_sell = sell_likelihood / (buy_likelihood + sell_likelihood)

# Decision rule
confidence_diff = abs(p_buy - p_sell)
if confidence_diff < 0.15:
    output_confidence = 0.45  # Uncertain - reduce position
elif confidence_diff < 0.30:
    output_confidence = 0.60  # Moderate uncertainty
else:
    output_confidence = 0.70-0.95  # Clear winner
```

**Key differences from WTA:**
1. **Doesn't throw away minority side** - it influences final confidence
2. **Uncertainty is encoded** - 50/50 split → lower confidence output
3. **No hard cutoff** - gradual confidence reduction as uncertainty increases
4. **Learning-based** - weights improve during backtesting

---

## Concrete Example: 2v2 Conflict with Learning

### Scenario
```
Market: "Will BTC > $50k?"
Arbitrage (0.75 conf): BUY  [Historical 55% accuracy]
Momentum (0.70 conf):  BUY  [Historical 52% accuracy]
Mean Reversion (0.68 conf): SELL  [Historical 61% accuracy]
Cross-Ex (0.65 conf):  SELL  [Historical 48% accuracy]
Current Regime: MEAN_REVERTING
```

### Old Algorithm (WTA)
```
buy_avg = (0.75 + 0.70) / 2 = 0.725
sell_avg = (0.68 + 0.65) / 2 = 0.665

0.725 > 0.665 → Output: BUY with 0.725 confidence
              → Throw away mean_reversion and cross_ex signals entirely
```

### New Algorithm (Bayesian + Regime + Learning)
```
# Step 1: Get regime weights (MEAN_REVERTING)
arb_weight_regime = 0.3      # Arb weak in mean-revert
momentum_weight_regime = 0.2
mr_weight_regime = 0.8       # MR strong in mean-revert
cross_weight_regime = 0.4

# Step 2: Adjust by historical accuracy
arb_weight = 0.3 * 0.55 = 0.165
momentum_weight = 0.2 * 0.52 = 0.104
mr_weight = 0.8 * 0.61 = 0.488
cross_weight = 0.4 * 0.48 = 0.192

# Step 3: Bayesian likelihood
buy_likelihood = (0.75 ^ 0.165) * (0.70 ^ 0.104) = 0.998
sell_likelihood = (0.68 ^ 0.488) * (0.65 ^ 0.192) = 0.651

# Step 4: Normalize
p_buy = 0.998 / (0.998 + 0.651) = 0.605
p_sell = 0.651 / (0.998 + 0.651) = 0.395

# Step 5: Confidence diff determines output confidence
confidence_diff = |0.605 - 0.395| = 0.210

Output: BUY (wins) but with confidence = 0.60 (not 0.725!)
        → Lower position size due to increased uncertainty
        → Reasoning: "Mean reversion signals have been more accurate
                      and are strong here, creating conflict uncertainty"
```

### Backtest Result
```
Market actual outcome: SELL (mean reversion was right)

Old algorithm: Lost $X (full position size on wrong side)
New algorithm: Lost $0.40X (60% confidence = reduced size)

Conflict recorded:
  ✓ Tracked that "2v2 in mean-revert regime" should favor SELL
  ✓ Updated that "MR > Momentum in this regime"
  ✓ Knows it's uncertainty scenario (2v2)
```

---

## Learning Mechanism

After backtesting, weights adapt:

```python
# Before backtesting
regime_weights['improved_momentum'][MarketRegime.MEAN_REVERTING] = 0.25

# After 500 conflicts in mean-revert regime
# Momentum went 2-for-10 times it was in minority (20%)
# Momentum went 15-for-50 times it was in majority (30%)
# Update down: 0.25 → 0.15 (less weight in this regime)

regime_weights['mean_reversion'][MarketRegime.MEAN_REVERTING] = 0.25
# Mean reversion went 8-for-10 times in minority (80%)
# Mean reversion went 40-for-50 times in majority (80%)
# Update up: 0.25 → 0.35 (more weight in this regime)
```

**Result:** Each backtesting run refines the regime weights.

---

## Implementation in Bot

### Replacement in Process Loop

**Before:**
```python
signals_by_agent = strategy_generation()
merged = consensus_engine.merge_signals(signals_by_agent)  # Old WTA
for signal in merged:
    execute(signal)
```

**After:**
```python
signals_by_agent = strategy_generation()
merged = intelligent_consensus.merge_signals_intelligent(
    signals_by_agent,
    market_state=market_data  # Enables regime detection
)

for signal in merged:
    if confidence_reduced_due_to_conflict:
        reduce_position_size_proportionally()

    execute(signal)

# After backtest outcome is known
for conflict in conflict_history:
    intelligent_consensus.record_outcome(
        conflict,
        actual_direction=actual_market_direction,
        pnl=realized_pnl
    )
```

### Intelligence Report Example

```python
report = intelligent_consensus.get_intelligence_report()

# Output:
{
    'total_conflicts': 1247,
    'strategy_stats': {
        'arbitrage': {
            'total_signals': 5000,
            'win_rate': 0.53,
            'conflict_signals': 300,
            'conflict_accuracy': 0.48,  # Worse in conflicts
        },
        'mean_reversion': {
            'total_signals': 4800,
            'win_rate': 0.62,
            'conflict_signals': 320,
            'conflict_accuracy': 0.71,  # Better in conflicts
        },
        # ... others
    },
    'regime_metrics': {
        'MARKET_1': {
            'current_regime': 'trending',
            'trend_strength': 0.45,
            'reversion_score': 0.12,
            'volatility': 0.14,
        },
    },
    'conflict_resolution_accuracy': 0.62,  # Overall conflict resolution rate
}
```

---

## Test Coverage

**15 tests verifying:**
- ✅ Regime detection (trending, mean-reverting, range-bound, high/low vol)
- ✅ Bayesian fusion with unanimous agreement (all strategies agree)
- ✅ Bayesian fusion with 2v2 conflicts (close calls reduce confidence)
- ✅ Bayesian fusion with 3v1 conflicts (clear majorities)
- ✅ Conflict logging and tracking
- ✅ Outcome recording and accuracy calculation
- ✅ Strategy statistics accumulation
- ✅ Regime-aware weighting
- ✅ Intelligence reporting

---

## Key Improvements Over WTA

| Aspect | Old WTA | Bayesian + Regime + Learning |
|--------|---------|------------------------------|
| Conflict resolution | Winner-take-all (discard minority) | Probabilistic (minority influences confidence) |
| Uncertainty handling | No | Yes (2v2 → 0.60 conf, 4v0 → 0.90 conf) |
| Regime awareness | No | Yes (weights per regime) |
| Historical learning | Logged but unused | Active (weights adapt) |
| Conflict tracking | Yes | Yes + outcome recording + accuracy |
| Position sizing on conflict | Full size | Reduced proportionally to uncertainty |
| Ensemble robustness | Low | High |

---

## Next Steps for Backtesting

1. **Generate backtest with learning enabled:**
   ```python
   bot = PredictionMarketBot(config)
   for historical_tick in backtest_data:
       signals = bot.process_market_tick(historical_tick)
       fills = bot.execute_signal(signals)

       # Record actual market direction for conflict learning
       for conflict in consensus_engine.conflict_history:
           consensus_engine.record_outcome(conflict, actual_direction)
   ```

2. **Extract intelligence report:**
   ```python
   report = bot.consensus_engine.get_intelligence_report()
   # Shows which strategies shine in which regimes
   # Shows conflict resolution accuracy patterns
   ```

3. **Retrain weights:** Use backtest intelligence to update regime_weights for next run

4. **Compare runs:**
   - Run 1: Default weights (25% each strategy per regime)
   - Run 2: After 1 backtest (weights adapted)
   - Run 3: After 2 backtests (further refined)
   - Compare Sharpe ratios and conflict accuracy

---

## Edge Cases Handled

1. **First 10 signals** (no regime confidence yet): Use default regime weights
2. **New market** (no historical data): Regime defaults to RANGE_BOUND
3. **Strategy not yet evaluated** (0 historical accuracy): Use regime weight as-is
4. **100% agreement** (4v0): High confidence output
5. **Extreme conflict** (2v2 with same confidence): Reduced confidence, may skip trade
6. **NaN/Inf in calculations**: Clipped to [0.1, 1.0] range

---

## Files

- `src/trading/intelligent_consensus.py` (400+ lines)
- `tests/test_intelligent_consensus.py` (470+ lines, 15 tests)

**Total: ~900 lines for Phase 4**
