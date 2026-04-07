"""Unit tests for volatility position sizing module"""

import unittest
import numpy as np
from datetime import datetime
from src.risk.volatility_position_sizing import (
    VolatilityCalculator,
    VolatilityAdjustedPositionSizer,
    DynamicRiskLimits,
)


class TestVolatilityCalculator(unittest.TestCase):
    """Test VolatilityCalculator class"""

    def setUp(self):
        self.calc = VolatilityCalculator(lookback_window=20)

    def test_add_price(self):
        """Test adding prices to history"""
        self.calc.add_price("MARKET_1", 0.50)
        self.assertEqual(len(self.calc.price_history["MARKET_1"]), 1)

        self.calc.add_price("MARKET_1", 0.51)
        self.assertEqual(len(self.calc.price_history["MARKET_1"]), 2)

    def test_calculate_volatility_insufficient_data(self):
        """Test volatility calculation with insufficient data"""
        self.calc.add_price("MARKET_1", 0.50)
        vol = self.calc.calculate_volatility("MARKET_1", datetime.utcnow())
        # Should return default 5% volatility
        self.assertEqual(vol, 0.05)

    def test_calculate_volatility_with_data(self):
        """Test volatility calculation with sufficient data"""
        prices = np.linspace(0.45, 0.55, 25)
        for price in prices:
            self.calc.add_price("MARKET_1", float(price))

        vol = self.calc.calculate_volatility("MARKET_1", datetime.utcnow())
        # Should be within reasonable bounds
        self.assertGreaterEqual(vol, 0.01)
        self.assertLess(vol, 0.5)

    def test_volatility_bounded(self):
        """Test that volatility is properly bounded"""
        # Add constant prices (zero volatility)
        for _ in range(25):
            self.calc.add_price("MARKET_1", 0.50)
        vol = self.calc.calculate_volatility("MARKET_1", datetime.utcnow())
        # Should be bounded at minimum 1%
        self.assertGreaterEqual(vol, 0.01)

    def test_calculate_half_life_insufficient_data(self):
        """Test half-life calculation with insufficient data"""
        self.calc.add_price("MARKET_1", 0.50)
        half_life = self.calc.calculate_half_life("MARKET_1")
        self.assertIsNone(half_life)

    def test_history_bounded(self):
        """Test that price history is bounded to avoid memory growth"""
        for i in range(100):
            self.calc.add_price("MARKET_1", 0.50 + 0.01 * np.sin(i / 10))
        # History should be bounded to lookback_window * 2
        self.assertLessEqual(len(self.calc.price_history["MARKET_1"]), 40)


class TestVolatilityAdjustedPositionSizer(unittest.TestCase):
    """Test VolatilityAdjustedPositionSizer class"""

    def setUp(self):
        self.sizer = VolatilityAdjustedPositionSizer(
            target_risk_pct=0.02,
            reference_volatility=0.1,
            kelly_fraction=0.25,
        )

    def test_initialize(self):
        """Test initialization with default parameters"""
        self.assertEqual(self.sizer.target_risk_pct, 0.02)
        self.assertEqual(self.sizer.reference_volatility, 0.1)
        self.assertEqual(self.sizer.kelly_fraction, 0.25)

    def test_update_volatility(self):
        """Test updating volatility estimates"""
        self.sizer.update_volatility("MARKET_1", 0.50)
        self.assertIn("MARKET_1", self.sizer.volatility_calc.price_history)

    def test_calculate_position_size_default_volatility(self):
        """Test position size calculation with default volatility"""
        size = self.sizer.calculate_position_size(
            market_id="MARKET_1",
            confidence=0.75,
            available_capital=100000,
        )
        # Should return a valid position size between 0 and 1
        self.assertGreaterEqual(size, 0.0)
        self.assertLessEqual(size, 1.0)

    def test_calculate_position_size_with_volatility(self):
        """Test position size calculation with explicit volatility"""
        size_low_vol = self.sizer.calculate_position_size(
            market_id="MARKET_1",
            confidence=0.75,
            available_capital=100000,
            current_volatility=0.05,
        )

        size_high_vol = self.sizer.calculate_position_size(
            market_id="MARKET_2",
            confidence=0.75,
            available_capital=100000,
            current_volatility=0.20,
        )

        # Lower volatility should result in larger position size
        self.assertGreater(size_low_vol, size_high_vol)

    def test_position_size_scales_with_confidence(self):
        """Test that position size scales with confidence"""
        size_low_conf = self.sizer.calculate_position_size(
            market_id="MARKET_1",
            confidence=0.5,
            available_capital=100000,
            current_volatility=0.10,
        )

        size_high_conf = self.sizer.calculate_position_size(
            market_id="MARKET_2",
            confidence=0.9,
            available_capital=100000,
            current_volatility=0.10,
        )

        # Higher confidence should result in larger position size
        self.assertGreater(size_high_conf, size_low_conf)

    def test_calculate_risk_parity_weights(self):
        """Test risk parity weight calculation"""
        volatilities = {"MARKET_1": 0.08, "MARKET_2": 0.12, "MARKET_3": 0.05}

        weights = self.sizer.calculate_risk_parity_weights(
            market_ids=["MARKET_1", "MARKET_2", "MARKET_3"],
            volatilities=volatilities,
        )

        # Weights should sum to 1.0
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=6)

        # Lower volatility markets should have higher weights
        self.assertGreater(weights["MARKET_3"], weights["MARKET_2"])
        self.assertGreater(weights["MARKET_1"], weights["MARKET_2"])

    def test_calculate_sharpe_adjusted_size(self):
        """Test Sharpe-adjusted position sizing"""
        size = self.sizer.calculate_sharpe_adjusted_size(
            market_id="MARKET_1",
            expected_return=0.05,
            volatility=0.10,
            risk_free_rate=0.02,
        )

        # Should return valid size
        self.assertGreaterEqual(size, 0.0)
        self.assertLessEqual(size, 1.0)

    def test_sharpe_adjusted_size_zero_volatility(self):
        """Test Sharpe adjustment with zero volatility"""
        size = self.sizer.calculate_sharpe_adjusted_size(
            market_id="MARKET_1",
            expected_return=0.05,
            volatility=0.0,
            risk_free_rate=0.02,
        )
        self.assertEqual(size, 0.0)


class TestDynamicRiskLimits(unittest.TestCase):
    """Test DynamicRiskLimits class"""

    def setUp(self):
        self.limits = DynamicRiskLimits(
            base_max_position_pct=0.05,
            base_max_daily_loss_pct=0.02,
            base_max_drawdown_pct=0.10,
        )

    def test_initialize(self):
        """Test initialization"""
        self.assertEqual(self.limits.base_max_position_pct, 0.05)
        self.assertEqual(self.limits.base_max_daily_loss_pct, 0.02)
        self.assertEqual(self.limits.base_max_drawdown_pct, 0.10)

    def test_update_drawdown(self):
        """Test drawdown update"""
        self.limits.update_drawdown(current_value=90000, peak_value=100000)
        self.assertAlmostEqual(self.limits.current_drawdown, 0.10, places=6)

    def test_drawdown_reduces_position_limits(self):
        """Test that drawdown reduces position limits"""
        no_drawdown_limit = self.limits.get_max_position_size()

        self.limits.update_drawdown(current_value=90000, peak_value=100000)
        with_drawdown_limit = self.limits.get_max_position_size()

        # Position limit should be smaller with drawdown
        self.assertLess(with_drawdown_limit, no_drawdown_limit)

    def test_volatility_adjustment(self):
        """Test volatility adjustment of limits"""
        # Low volatility (safer)
        self.limits.set_volatility_adjustment(volatility=0.05, reference_vol=0.1)
        size_low_vol = self.limits.get_max_position_size()

        # High volatility (riskier)
        self.limits.set_volatility_adjustment(volatility=0.20, reference_vol=0.1)
        size_high_vol = self.limits.get_max_position_size()

        # Higher volatility should have smaller position limits
        self.assertGreater(size_low_vol, size_high_vol)

    def test_is_trading_allowed(self):
        """Test trading allowed check"""
        # Should be allowed initially
        self.assertTrue(self.limits.is_trading_allowed())

        # Exceed drawdown limit
        self.limits.update_drawdown(current_value=80000, peak_value=100000)
        self.assertFalse(self.limits.is_trading_allowed())

    def test_daily_loss_check(self):
        """Test daily loss limit enforcement"""
        self.limits.update_daily_pnl(-0.03)  # 3% daily loss
        self.assertFalse(self.limits.is_trading_allowed())

        self.limits.update_daily_pnl(-0.01)  # 1% daily loss
        self.assertTrue(self.limits.is_trading_allowed())


if __name__ == "__main__":
    unittest.main()
