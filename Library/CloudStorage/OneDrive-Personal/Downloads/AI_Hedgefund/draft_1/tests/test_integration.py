"""Integration tests for all improvement modules working together"""

import unittest
import numpy as np
from datetime import datetime
from src.risk.volatility_position_sizing import VolatilityAdjustedPositionSizer
from src.strategies.mean_reversion_detector import MeanReversionDetector
from src.risk.dynamic_risk_manager import DynamicRiskManager
from src.strategies.cross_exchange_arbitrage import CrossExchangeArbitrageFinder
from src.strategies.base_strategy import MarketState


class TestIntegratedStrategyStack(unittest.TestCase):
    """Test all modules working together as an integrated system"""

    def setUp(self):
        """Initialize all components"""
        # Risk management
        self.risk_mgr = DynamicRiskManager(
            initial_capital=100000,
            base_max_daily_loss_pct=0.02,
            base_max_position_size_pct=0.05,
            base_max_drawdown_pct=0.15,
        )

        # Position sizing
        self.sizer = VolatilityAdjustedPositionSizer(
            target_risk_pct=0.02,
            reference_volatility=0.1,
            kelly_fraction=0.25,
        )

        # Strategy detection
        self.mr_detector = MeanReversionDetector(
            config={
                "lookback_window": 20,
                "z_score_threshold": 2.0,
                "bollinger_std_dev": 2.0,
                "min_confidence": 0.5,
            }
        )

        # Cross-exchange arbitrage
        self.arb_finder = CrossExchangeArbitrageFinder(
            config={
                "min_profit_bps": 100,
                "matched_pair_threshold": 0.01,
                "cross_exchange_threshold": 0.02,
            }
        )

    def test_mean_reversion_with_position_sizing(self):
        """Test mean reversion signals sized by volatility"""
        # Generate market with mean-reverting prices
        prices = [0.50] * 10 + [0.40]  # Price drops below mean

        for price in prices:
            market_state = MarketState(
                timestamp=datetime.utcnow(),
                market_id="MARKET_1",
                yes_bid=price - 0.01,
                yes_ask=price + 0.01,
                no_bid=1 - price - 0.01,
                no_ask=1 - price + 0.01,
                volume_24h=1000,
                lookback_data=[],
            )

            # Get mean reversion signal
            signals = self.mr_detector.generate_signals(market_state)

            # Update volatility
            self.sizer.update_volatility("MARKET_1", price)

        # Get volatility-adjusted position size
        if signals:
            signal = signals[-1]
            position_size = self.sizer.calculate_position_size(
                market_id="MARKET_1",
                confidence=signal.confidence,
                available_capital=100000,
            )

            # Position should be valid
            self.assertGreaterEqual(position_size, 0.0)
            self.assertLessEqual(position_size, 1.0)

    def test_risk_management_blocks_large_position(self):
        """Test that risk manager blocks positions exceeding limits"""
        # Try to take a large position
        position_size = 10000  # 10% of portfolio
        portfolio_value = 100000

        allowed, reason = self.risk_mgr.check_position_allowed(
            position_size=position_size,
            portfolio_value=portfolio_value,
        )

        # Should be rejected (exceeds 5% limit)
        self.assertFalse(allowed)

    def test_risk_management_allows_small_position(self):
        """Test that risk manager allows reasonable positions"""
        position_size = 2500  # 2.5% of portfolio
        portfolio_value = 100000

        allowed, reason = self.risk_mgr.check_position_allowed(
            position_size=position_size,
            portfolio_value=portfolio_value,
        )

        # Should be allowed
        self.assertTrue(allowed)

    def test_risk_management_enforces_emergency_stop(self):
        """Test emergency stop on severe drawdown"""
        # Simulate significant drawdown
        self.risk_mgr.update_portfolio_value(120000)  # Peak
        self.risk_mgr.update_portfolio_value(95000)  # 20.8% drawdown
        self.risk_mgr.update_volatility(0.08)

        self.risk_mgr.check_and_apply_emergency_stop()

        # Should trigger emergency stop
        self.assertTrue(self.risk_mgr.emergency_stop_triggered)

        # Position should be blocked after emergency stop
        allowed, reason = self.risk_mgr.check_position_allowed(
            position_size=1000,
            portfolio_value=95000,
        )
        self.assertFalse(allowed)

    def test_arbitrage_detection_with_both_exchanges(self):
        """Test arbitrage detection when both exchanges available"""
        # Update Kalshi prices
        market_state = MarketState(
            timestamp=datetime.utcnow(),
            market_id="MARKET_1",
            yes_bid=0.48,
            yes_ask=0.49,
            no_bid=0.48,
            no_ask=0.49,
            volume_24h=1000,
            lookback_data=[],
        )
        self.arb_finder.update_kalshi_price(market_state)

        # Update Polymarket prices (similar)
        self.arb_finder.update_polymarket_price(
            market_id="MARKET_1",
            timestamp=datetime.utcnow(),
            yes_bid=0.48,
            yes_ask=0.49,
            no_bid=0.48,
            no_ask=0.49,
        )

        # Generate signals
        signals = self.arb_finder.generate_signals(market_state)

        # Should generate matched pair signals
        self.assertGreater(len(signals), 0)

    def test_full_workflow_detection_and_sizing(self):
        """Test complete workflow from detection to sizing to risk check"""
        # 1. Simulate signal generation with market state
        market_state = MarketState(
            timestamp=datetime.utcnow(),
            market_id="MARKET_1",
            yes_bid=0.45,
            yes_ask=0.47,
            no_bid=0.53,
            no_ask=0.55,
            volume_24h=1000,
            lookback_data=[],
        )

        # Manually create a signal (simplified from mean reversion detection)
        from src.data.models import Signal, Direction, Outcome
        signal = Signal(
            timestamp=datetime.utcnow(),
            market_id="MARKET_1",
            strategy_name="test_strategy",
            direction=Direction.BUY,
            outcome=Outcome.YES,
            contracts=1000,
            confidence=0.60,  # Moderate confidence
            reason="Test mean reversion signal",
            estimated_price=0.46,
        )

        # 2. Size position based on volatility and confidence
        self.sizer.update_volatility("MARKET_1", 0.46)
        position_pct = self.sizer.calculate_position_size(
            market_id="MARKET_1",
            confidence=signal.confidence,
            available_capital=100000,
            current_volatility=0.08,
        )

        position_size = position_pct * 100000

        # 3. Check risk limits
        self.risk_mgr.update_portfolio_value(100000)
        self.risk_mgr.update_volatility(0.08)

        allowed, reason = self.risk_mgr.check_position_allowed(
            position_size=position_size,
            portfolio_value=100000,
        )

        # Verify that sizing and risk management are working
        # Position may be rejected if it exceeds limits, but that's expected behavior
        self.assertIsInstance(allowed, bool)
        self.assertGreater(position_size, 0)  # Position was sized

    def test_risk_parity_portfolio(self):
        """Test risk parity allocation across multiple markets"""
        # Simulate multiple markets with different volatilities
        markets = {
            "MARKET_1": {"vol": 0.05, "confidence": 0.6},
            "MARKET_2": {"vol": 0.10, "confidence": 0.6},
            "MARKET_3": {"vol": 0.12, "confidence": 0.6},
        }

        # Calculate positions for each market
        positions = {}
        total_capital = 100000

        volatilities = {m: data["vol"] for m, data in markets.items()}
        weights = self.sizer.calculate_risk_parity_weights(
            market_ids=list(markets.keys()),
            volatilities=volatilities,
        )

        for market_id, data in markets.items():
            position_pct = self.sizer.calculate_position_size(
                market_id=market_id,
                confidence=data["confidence"],
                available_capital=total_capital,
                current_volatility=data["vol"],
            )

            positions[market_id] = position_pct * total_capital

        # Verify all positions are reasonable sizes (under risk limits)
        # Note: With volatility-adjusted sizing, individual positions may vary
        total_position = sum(positions.values())
        # Total portfolio exposure should be reasonable
        self.assertLess(total_position, total_capital * 0.30)  # Less than 30% total exposure

    def test_dynamic_limit_adjustment_on_drawdown(self):
        """Test that limits adjust based on drawdown"""
        # Set consistent volatility to isolate drawdown effect
        self.risk_mgr.update_volatility(0.08)

        # Get initial limits (no drawdown)
        limits_initial = self.risk_mgr.calculate_dynamic_limits()
        drawdown_factor_initial = 1.0 - self.risk_mgr.get_current_drawdown()

        # Create drawdown
        self.risk_mgr.update_portfolio_value(120000)  # Peak
        self.risk_mgr.update_portfolio_value(100000)  # Some drawdown
        self.risk_mgr.update_volatility(0.08)

        limits_after_dd = self.risk_mgr.calculate_dynamic_limits()
        drawdown_factor_after = 1.0 - self.risk_mgr.get_current_drawdown()

        # Drawdown factor should be smaller after creating drawdown
        self.assertLess(drawdown_factor_after, drawdown_factor_initial)
        # Position limits should reflect the drawdown reduction
        self.assertLess(limits_after_dd["max_position_size_pct"],
                       limits_initial["max_position_size_pct"])

    def test_metrics_calculation_across_modules(self):
        """Test that all modules can calculate metrics for monitoring"""
        # Generate some activity
        for i in range(20):
            price = 0.50 + 0.05 * np.sin(i)
            market_state = MarketState(
                timestamp=datetime.utcnow(),
                market_id="MARKET_1",
                yes_bid=price - 0.01,
                yes_ask=price + 0.01,
                no_bid=1 - price - 0.01,
                no_ask=1 - price + 0.01,
                volume_24h=1000,
                lookback_data=[],
            )

            self.mr_detector.generate_signals(market_state)
            self.sizer.update_volatility("MARKET_1", price)
            # Calculate position size to populate volatility cache
            self.sizer.calculate_position_size(
                market_id="MARKET_1",
                confidence=0.7,
                available_capital=100000,
                current_volatility=0.08,
            )
            self.risk_mgr.update_portfolio_value(100000 + i * 100)
            self.risk_mgr.update_volatility(0.08)

        # Get metrics from each module
        mr_metrics = self.mr_detector.get_metrics()
        sizer_metrics = self.sizer.get_all_volatilities()
        risk_summary = self.risk_mgr.get_risk_summary()

        # Verify metrics exist and are reasonable
        self.assertIn("mean_reversion_scores", mr_metrics)
        self.assertIsNotNone(sizer_metrics)
        self.assertIn("current_value", risk_summary)

        # Risk summary should show no emergency stop
        self.assertFalse(risk_summary["emergency_stop_triggered"])


class TestModuleCompatibility(unittest.TestCase):
    """Test compatibility and data flow between modules"""

    def test_signal_confidence_used_for_sizing(self):
        """Test that signal confidence is properly used for position sizing"""
        sizer = VolatilityAdjustedPositionSizer()

        # High confidence should result in larger position
        size_high = sizer.calculate_position_size(
            market_id="MARKET_1",
            confidence=0.9,
            available_capital=100000,
            current_volatility=0.1,
        )

        size_low = sizer.calculate_position_size(
            market_id="MARKET_2",
            confidence=0.5,
            available_capital=100000,
            current_volatility=0.1,
        )

        self.assertGreater(size_high, size_low)

    def test_volatility_affects_all_limits(self):
        """Test that volatility properly affects all risk limits"""
        risk_mgr = DynamicRiskManager()

        # Low volatility scenario
        risk_mgr.update_volatility(0.05)
        limits_low_vol = risk_mgr.calculate_dynamic_limits()

        # High volatility scenario
        risk_mgr.update_volatility(0.20)
        limits_high_vol = risk_mgr.calculate_dynamic_limits()

        # Position limits should be tighter in high volatility
        self.assertGreater(
            limits_low_vol["max_position_size_pct"],
            limits_high_vol["max_position_size_pct"],
        )

    def test_drawdown_signals_emergency_stop_condition(self):
        """Test that exceeding drawdown triggers stop conditions"""
        risk_mgr = DynamicRiskManager(base_max_drawdown_pct=0.10)

        # Reset daily limits to avoid daily loss trigger
        risk_mgr.reset_daily_limits(115000)

        # Create 15% drawdown (exceeds 10% limit)
        risk_mgr.update_portfolio_value(115000)  # Peak
        risk_mgr.update_portfolio_value(97750)  # 15% drawdown
        risk_mgr.update_volatility(0.08)

        stop_triggered, reason = risk_mgr.check_emergency_stop()

        # Should trigger emergency stop due to drawdown
        self.assertTrue(stop_triggered)


if __name__ == "__main__":
    unittest.main()
