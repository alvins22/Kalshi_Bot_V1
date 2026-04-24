"""
Tests for Bayesian position sizing module

Bayesian Position Sizing improves Kelly Criterion by accounting for uncertainty
in win rate estimation. Expected: +10-15% Sharpe ratio improvement.
"""

import unittest
import numpy as np
from src.risk.bayesian_position_sizing import BayesianPositionSizer, BayesianWinEstimate


class TestBayesianWinEstimate(unittest.TestCase):
    """Test BayesianWinEstimate dataclass"""

    def test_create_estimate(self):
        """Test creating a Bayesian estimate"""
        estimate = BayesianWinEstimate(
            posterior_mean=0.6,
            posterior_std=0.05,
            credible_interval_lower=0.51,
            credible_interval_upper=0.69,
            confidence=0.8,
        )

        self.assertEqual(estimate.posterior_mean, 0.6)
        self.assertGreaterEqual(estimate.credible_interval_upper, estimate.posterior_mean)
        self.assertLessEqual(estimate.credible_interval_lower, estimate.posterior_mean)


class TestBayesianPositionSizer(unittest.TestCase):
    """Test BayesianPositionSizer class"""

    def setUp(self):
        """Initialize sizer for tests"""
        self.sizer = BayesianPositionSizer(
            kelly_fraction=0.25,
            min_trades_for_full_size=30,
        )

    def test_initialization(self):
        """Test sizer initialization"""
        self.assertEqual(self.sizer.kelly_fraction, 0.25)
        self.assertEqual(self.sizer.min_trades_for_full_size, 30)
        self.assertEqual(len(self.sizer.strategy_wins), 0)

    def test_update_strategy_performance(self):
        """Test updating strategy performance"""
        self.sizer.update_strategy_performance("strategy_a", wins=10, losses=5)

        self.assertEqual(self.sizer.strategy_wins["strategy_a"], 10)
        self.assertEqual(self.sizer.strategy_losses["strategy_a"], 5)

    def test_estimate_win_probability_no_data(self):
        """Test estimate with no historical data"""
        estimate = self.sizer.estimate_win_probability("unknown_strategy")

        # With uniform prior and no data, posterior should be 0.5
        self.assertAlmostEqual(estimate.posterior_mean, 0.5, places=3)
        self.assertGreater(estimate.posterior_std, 0)

    def test_estimate_win_probability_with_data(self):
        """Test estimate with historical win/loss data"""
        self.sizer.update_strategy_performance("strategy_a", wins=20, losses=5)

        estimate = self.sizer.estimate_win_probability("strategy_a")

        # Posterior should shift towards empirical win rate
        empirical_wr = 20 / 25
        self.assertGreater(estimate.posterior_mean, 0.5)
        self.assertLess(estimate.posterior_std, 0.1)  # More data = lower uncertainty
        self.assertGreater(estimate.confidence, 0.5)  # Some confidence with 25 trades

    def test_estimate_more_data_reduces_uncertainty(self):
        """Test that more data reduces posterior uncertainty"""
        # Few trades
        self.sizer.update_strategy_performance("strategy_a", wins=10, losses=5)
        estimate_few = self.sizer.estimate_win_probability("strategy_a")

        # Many trades (same ratio)
        self.sizer.update_strategy_performance("strategy_b", wins=100, losses=50)
        estimate_many = self.sizer.estimate_win_probability("strategy_b")

        # With same ratio, posterior means should be close but may differ slightly due to prior
        # (Beta prior has more influence with fewer samples)
        self.assertAlmostEqual(estimate_few.posterior_mean, estimate_many.posterior_mean, places=1)
        # More data should reduce uncertainty
        self.assertGreater(estimate_few.posterior_std, estimate_many.posterior_std)
        self.assertGreater(estimate_many.confidence, estimate_few.confidence)

    def test_credible_interval_bounds(self):
        """Test credible interval is valid"""
        self.sizer.update_strategy_performance("strategy_a", wins=30, losses=20)
        estimate = self.sizer.estimate_win_probability("strategy_a")

        # Interval should contain mean
        self.assertLessEqual(estimate.credible_interval_lower, estimate.posterior_mean)
        self.assertGreaterEqual(estimate.credible_interval_upper, estimate.posterior_mean)

        # Interval should be in [0, 1]
        self.assertGreaterEqual(estimate.credible_interval_lower, 0.0)
        self.assertLessEqual(estimate.credible_interval_upper, 1.0)

    def test_calculate_kelly_fraction_high_win_rate(self):
        """Test Kelly calculation with high win rate"""
        self.sizer.update_strategy_performance("winner", wins=70, losses=30)

        kelly = self.sizer.calculate_kelly_fraction("winner")

        # High win rate should give positive Kelly fraction
        self.assertGreater(kelly, 0.0)
        self.assertLessEqual(kelly, 1.0)

    def test_calculate_kelly_fraction_low_win_rate(self):
        """Test Kelly calculation with low win rate"""
        self.sizer.update_strategy_performance("loser", wins=30, losses=70)

        kelly = self.sizer.calculate_kelly_fraction("loser")

        # Low win rate should give near-zero Kelly
        self.assertGreaterEqual(kelly, 0.0)
        self.assertLess(kelly, 0.1)

    def test_kelly_fraction_bounded(self):
        """Test Kelly fraction is always bounded [0, 1]"""
        self.sizer.update_strategy_performance("strategy_a", wins=50, losses=50)
        self.sizer.update_strategy_performance("strategy_b", wins=100, losses=1)

        kelly_a = self.sizer.calculate_kelly_fraction("strategy_a")
        kelly_b = self.sizer.calculate_kelly_fraction("strategy_b")

        self.assertGreaterEqual(kelly_a, 0.0)
        self.assertLessEqual(kelly_a, 1.0)
        self.assertGreaterEqual(kelly_b, 0.0)
        self.assertLessEqual(kelly_b, 1.0)

    def test_bayesian_damping_with_few_trades(self):
        """Test that Kelly is damped when few trades"""
        self.sizer.update_strategy_performance("few_trades", wins=3, losses=1)

        estimate = self.sizer.estimate_win_probability("few_trades")
        self.assertLess(estimate.confidence, 0.5)  # Low confidence

        kelly = self.sizer.calculate_kelly_fraction("few_trades")
        # Should be small due to low confidence damping
        self.assertLess(kelly, 0.2)

    def test_bayesian_damping_with_many_trades(self):
        """Test that Kelly approaches full value with many trades"""
        self.sizer.update_strategy_performance("many_trades", wins=80, losses=20)

        estimate = self.sizer.estimate_win_probability("many_trades")
        self.assertGreater(estimate.confidence, 0.8)  # High confidence

        kelly = self.sizer.calculate_kelly_fraction("many_trades")
        # Should be larger due to high confidence
        self.assertGreater(kelly, 0.05)

    def test_adaptive_position_size(self):
        """Test adaptive position size combining Kelly and signal confidence"""
        self.sizer.update_strategy_performance("strategy_a", wins=60, losses=40)

        # High signal confidence
        size_high = self.sizer.get_adaptive_position_size(
            strategy_name="strategy_a",
            base_size=0.5,
            signal_confidence=0.9,
        )

        # Low signal confidence
        size_low = self.sizer.get_adaptive_position_size(
            strategy_name="strategy_a",
            base_size=0.5,
            signal_confidence=0.3,
        )

        # High confidence should give larger position
        self.assertGreater(size_high, size_low)
        self.assertLessEqual(size_high, 1.0)
        self.assertGreaterEqual(size_low, 0.0)

    def test_payoff_ratio_effect(self):
        """Test that payoff ratio affects Kelly calculation"""
        self.sizer.update_strategy_performance("strategy_a", wins=55, losses=45)

        # Fair game: ratio = 1.0
        kelly_fair = self.sizer.calculate_kelly_fraction("strategy_a", payoff_ratio=1.0)

        # Favorable game: ratio = 2.0 (win twice the loss amount)
        kelly_favorable = self.sizer.calculate_kelly_fraction("strategy_a", payoff_ratio=2.0)

        # Favorable odds should give larger Kelly
        self.assertGreater(kelly_favorable, kelly_fair)

    def test_get_estimate_summary(self):
        """Test getting summary of Bayesian estimate"""
        self.sizer.update_strategy_performance("strategy_a", wins=40, losses=10)

        summary = self.sizer.get_estimate_summary("strategy_a")

        self.assertEqual(summary["n_trades"], 50)
        self.assertAlmostEqual(summary["empirical_win_rate"], 0.8, places=3)
        self.assertGreater(summary["posterior_mean"], 0.7)
        self.assertGreater(summary["confidence"], 0.5)
        self.assertIn("kelly_fraction", summary)

    def test_edge_case_zero_trades(self):
        """Test edge case with zero trades"""
        estimate = self.sizer.estimate_win_probability("no_data")
        kelly = self.sizer.calculate_kelly_fraction("no_data")

        # Should default to 0.5 and minimal position
        self.assertAlmostEqual(estimate.posterior_mean, 0.5, places=3)
        self.assertEqual(kelly, 0.0)  # Can't trade without win probability


class TestBayesianIntegration(unittest.TestCase):
    """Integration tests for Bayesian sizing"""

    def test_full_workflow(self):
        """Test complete workflow: track → estimate → size"""
        sizer = BayesianPositionSizer(kelly_fraction=0.25)

        # Simulate trading several strategies
        strategies = {
            "arbitrage": (70, 20),  # High win rate
            "momentum": (55, 45),   # Moderate
            "mean_reversion": (45, 55),  # Low
        }

        for name, (wins, losses) in strategies.items():
            sizer.update_strategy_performance(name, wins=wins, losses=losses)

        # Get sizing for each
        sizes = {}
        for name in strategies.keys():
            size = sizer.get_adaptive_position_size(
                strategy_name=name,
                base_size=0.1,
                signal_confidence=0.7,
            )
            sizes[name] = size

        # Arbitrage should get largest position
        self.assertGreater(sizes["arbitrage"], sizes["momentum"])
        self.assertGreater(sizes["momentum"], sizes["mean_reversion"])

    def test_multiple_strategies_allocation(self):
        """Test capital allocation across strategies"""
        sizer = BayesianPositionSizer()

        # Three strategies with different quality
        sizer.update_strategy_performance("good", wins=70, losses=30)
        sizer.update_strategy_performance("medium", wins=55, losses=45)
        sizer.update_strategy_performance("poor", wins=45, losses=55)

        # Get adaptive sizes
        size_good = sizer.calculate_kelly_fraction("good")
        size_medium = sizer.calculate_kelly_fraction("medium")
        size_poor = sizer.calculate_kelly_fraction("poor")

        # Should prioritize good strategy
        self.assertGreater(size_good, size_medium)
        self.assertGreater(size_medium, size_poor)


if __name__ == "__main__":
    unittest.main()
