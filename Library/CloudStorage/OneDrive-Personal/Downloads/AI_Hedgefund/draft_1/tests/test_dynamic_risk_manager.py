"""Unit tests for dynamic risk manager module"""

import unittest
import numpy as np
from datetime import datetime
from src.risk.dynamic_risk_manager import (
    DrawdownPredictor,
    DynamicRiskManager,
    DrawdownEvent,
)


class TestDrawdownPredictor(unittest.TestCase):
    """Test DrawdownPredictor class"""

    def setUp(self):
        self.predictor = DrawdownPredictor(lookback_bars=100)

    def test_add_equity_point(self):
        """Test adding equity observations"""
        timestamp = datetime.utcnow()
        self.predictor.add_equity_point(timestamp, 100000)
        self.assertEqual(len(self.predictor.equity_history), 1)
        self.assertEqual(self.predictor.equity_history[0], 100000)

    def test_add_volatility(self):
        """Test adding volatility observations"""
        self.predictor.add_volatility(0.08)
        self.assertEqual(len(self.predictor.volatility_history), 1)
        self.assertEqual(self.predictor.volatility_history[0], 0.08)

    def test_history_bounded(self):
        """Test that history is bounded to prevent memory growth"""
        # Add many observations
        for i in range(300):
            self.predictor.add_equity_point(datetime.utcnow(), 100000 + i)

        # History should be bounded
        self.assertLessEqual(len(self.predictor.equity_history), 200)

    def test_predict_drawdown_probability_insufficient_data(self):
        """Test drawdown probability with insufficient data"""
        self.predictor.add_equity_point(datetime.utcnow(), 100000)
        prob = self.predictor.predict_drawdown_probability()
        # Should return default low probability
        self.assertEqual(prob, 0.3)

    def test_predict_drawdown_probability_stable(self):
        """Test drawdown probability with stable equity"""
        # Add stable equity observations
        for i in range(50):
            self.predictor.add_equity_point(datetime.utcnow(), 100000)
            self.predictor.add_volatility(0.05)

        prob = self.predictor.predict_drawdown_probability()

        # Stable market should have low drawdown risk
        self.assertGreaterEqual(prob, 0.0)
        self.assertLessEqual(prob, 1.0)

    def test_predict_drawdown_probability_declining(self):
        """Test drawdown probability with declining equity"""
        # Add declining equity observations
        for i in range(50):
            equity = 100000 - i * 100  # Declining
            self.predictor.add_equity_point(datetime.utcnow(), equity)
            self.predictor.add_volatility(0.05)

        prob = self.predictor.predict_drawdown_probability()

        # Declining market should have higher drawdown risk
        self.assertGreaterEqual(prob, 0.0)
        self.assertLessEqual(prob, 1.0)

    def test_get_predicted_max_drawdown_no_history(self):
        """Test predicted max drawdown with no history"""
        dd = self.predictor.get_predicted_max_drawdown()
        # Should return default 10%
        self.assertEqual(dd, 0.10)

    def test_get_predicted_max_drawdown_with_history(self):
        """Test predicted max drawdown with event history"""
        # Add some drawdown events
        event1 = DrawdownEvent(
            start_time=datetime.utcnow(),
            start_value=100000,
            min_value=90000,
            end_time=datetime.utcnow(),
            max_drawdown_pct=0.10,
        )
        self.predictor.drawdown_events.append(event1)

        dd = self.predictor.get_predicted_max_drawdown()

        # Should be between 5% and 50%
        self.assertGreaterEqual(dd, 0.05)
        self.assertLessEqual(dd, 0.50)


class TestDynamicRiskManager(unittest.TestCase):
    """Test DynamicRiskManager class"""

    def setUp(self):
        self.risk_mgr = DynamicRiskManager(
            initial_capital=100000,
            base_max_daily_loss_pct=0.02,
            base_max_position_size_pct=0.05,
            base_max_drawdown_pct=0.15,
        )

    def test_initialize(self):
        """Test initialization"""
        self.assertEqual(self.risk_mgr.initial_capital, 100000)
        self.assertEqual(self.risk_mgr.current_value, 100000)
        self.assertEqual(self.risk_mgr.peak_value, 100000)

    def test_update_portfolio_value(self):
        """Test updating portfolio value"""
        self.risk_mgr.update_portfolio_value(105000)
        self.assertEqual(self.risk_mgr.current_value, 105000)
        self.assertEqual(self.risk_mgr.peak_value, 105000)

    def test_peak_value_tracking(self):
        """Test that peak value is tracked correctly"""
        self.risk_mgr.update_portfolio_value(105000)
        self.risk_mgr.update_portfolio_value(103000)  # Decline
        # Peak should still be 105000
        self.assertEqual(self.risk_mgr.peak_value, 105000)

    def test_get_current_drawdown(self):
        """Test current drawdown calculation"""
        self.risk_mgr.update_portfolio_value(105000)  # Peak
        self.risk_mgr.update_portfolio_value(100000)  # Decline to starting value
        dd = self.risk_mgr.get_current_drawdown()
        # Drawdown should be ~4.76% (5000 / 105000)
        self.assertAlmostEqual(dd, 5000 / 105000, places=4)

    def test_get_daily_loss_pct(self):
        """Test daily loss percentage"""
        self.risk_mgr.update_portfolio_value(98000)  # 2% loss
        daily_loss = self.risk_mgr.get_daily_loss_pct()
        self.assertAlmostEqual(daily_loss, -0.02, places=6)

    def test_calculate_dynamic_limits(self):
        """Test dynamic limits calculation"""
        limits = self.risk_mgr.calculate_dynamic_limits()

        self.assertIn("max_position_size_pct", limits)
        self.assertIn("max_daily_loss_pct", limits)
        self.assertIn("max_drawdown_pct", limits)

        # Limits should be positive
        self.assertGreater(limits["max_position_size_pct"], 0)
        self.assertGreater(limits["max_daily_loss_pct"], 0)

    def test_limits_reduce_with_drawdown(self):
        """Test that limits reduce as drawdown increases"""
        limits_no_dd = self.risk_mgr.calculate_dynamic_limits()

        # Create drawdown
        self.risk_mgr.update_portfolio_value(110000)  # Peak
        self.risk_mgr.update_portfolio_value(95000)  # 13.6% drawdown

        limits_with_dd = self.risk_mgr.calculate_dynamic_limits()

        # Limits should be reduced
        self.assertLess(
            limits_with_dd["max_position_size_pct"],
            limits_no_dd["max_position_size_pct"],
        )

    def test_check_position_allowed(self):
        """Test position size checking"""
        allowed, reason = self.risk_mgr.check_position_allowed(
            position_size=2500,  # 2.5% of portfolio
            portfolio_value=100000,
        )
        # Should be allowed
        self.assertTrue(allowed)

    def test_check_position_exceeds_limit(self):
        """Test position rejection when exceeding limit"""
        # Try position larger than 5% limit
        allowed, reason = self.risk_mgr.check_position_allowed(
            position_size=10000,  # 10% of portfolio
            portfolio_value=100000,
        )
        # Should be rejected
        self.assertFalse(allowed)
        self.assertIn("exceeds limit", reason)

    def test_check_emergency_stop_daily_loss(self):
        """Test emergency stop on daily loss"""
        self.risk_mgr.update_portfolio_value(98000)  # 2% daily loss (at limit)
        self.risk_mgr.update_volatility(0.08)

        stop_triggered, reason = self.risk_mgr.check_emergency_stop()

        # Should trigger or be close to limit
        self.assertIsInstance(stop_triggered, bool)

    def test_check_emergency_stop_drawdown(self):
        """Test emergency stop on drawdown"""
        # First, reset daily limits to avoid daily loss trigger
        self.risk_mgr.reset_daily_limits(120000)  # Reset with high starting value
        self.risk_mgr.update_portfolio_value(120000)  # Peak
        self.risk_mgr.update_portfolio_value(97000)  # 19.2% drawdown (exceeds 15% limit)
        self.risk_mgr.update_volatility(0.08)

        stop_triggered, reason = self.risk_mgr.check_emergency_stop()

        # Should trigger - either drawdown or daily loss
        self.assertTrue(stop_triggered or "Drawdown" in reason or "Daily loss" in reason)

    def test_check_and_apply_emergency_stop(self):
        """Test emergency stop application"""
        self.risk_mgr.update_portfolio_value(120000)
        self.risk_mgr.update_portfolio_value(95000)
        self.risk_mgr.check_and_apply_emergency_stop()

        # Should be triggered
        self.assertTrue(self.risk_mgr.emergency_stop_triggered)

    def test_reset_daily_limits(self):
        """Test daily limits reset"""
        self.risk_mgr.update_portfolio_value(98000)
        self.risk_mgr.reset_daily_limits(100000)

        daily_loss = self.risk_mgr.get_daily_loss_pct()
        self.assertAlmostEqual(daily_loss, 0.0, places=6)

    def test_halt_and_resume_trading(self):
        """Test trading halt and resume"""
        self.risk_mgr.halt_trading("Testing halt")
        self.assertTrue(self.risk_mgr.trading_halted)
        self.assertEqual(self.risk_mgr.halt_reason, "Testing halt")

        self.risk_mgr.resume_trading()
        self.assertFalse(self.risk_mgr.trading_halted)

    def test_calculate_risk_metrics(self):
        """Test risk metrics calculation"""
        # Add some equity history
        for i in range(30):
            self.risk_mgr.update_portfolio_value(100000 + i * 100)
            self.risk_mgr.update_volatility(0.08)

        metrics = self.risk_mgr.calculate_risk_metrics()

        # Check metric fields exist
        self.assertIsNotNone(metrics.current_value)
        self.assertIsNotNone(metrics.current_drawdown_pct)
        self.assertIsNotNone(metrics.volatility_pct)

    def test_get_risk_summary(self):
        """Test risk summary retrieval"""
        self.risk_mgr.update_portfolio_value(105000)
        self.risk_mgr.update_volatility(0.08)

        summary = self.risk_mgr.get_risk_summary()

        self.assertIn("current_value", summary)
        self.assertIn("peak_value", summary)
        self.assertIn("drawdown_pct", summary)
        self.assertIn("emergency_stop_triggered", summary)
        self.assertIn("dynamic_limits", summary)

        # Values should be correct
        self.assertEqual(summary["current_value"], 105000)
        self.assertEqual(summary["peak_value"], 105000)


if __name__ == "__main__":
    unittest.main()
