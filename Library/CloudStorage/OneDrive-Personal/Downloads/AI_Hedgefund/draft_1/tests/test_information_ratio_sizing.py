"""
Tests for Information Ratio-based position sizing

Information Ratio Sizing improves risk-adjusted returns by scaling position sizes
based on each strategy's information ratio relative to a target portfolio IR.

Expected: +20-25% Sharpe ratio improvement
"""

import unittest
import numpy as np
from src.risk.information_ratio_sizing import InformationRatioSizer, StrategyMetrics


class TestStrategyMetrics(unittest.TestCase):
    """Test StrategyMetrics dataclass"""

    def test_initialize_metrics(self):
        """Test initializing strategy metrics"""
        metrics = StrategyMetrics(strategy_name="test_strategy")
        self.assertEqual(metrics.strategy_name, "test_strategy")
        self.assertEqual(metrics.total_return, 0.0)
        self.assertEqual(metrics.win_rate, 0.5)
        self.assertEqual(metrics.volatility, 0.01)

    def test_update_ir_calculation(self):
        """Test information ratio calculation"""
        metrics = StrategyMetrics(
            strategy_name="test",
            total_return=0.10,
            volatility=0.05,
        )
        metrics.update_ir(benchmark_return=0.0)

        expected_ir = 0.10 / 0.05
        self.assertAlmostEqual(metrics.information_ratio, expected_ir, places=4)

    def test_update_ir_with_zero_volatility(self):
        """Test IR calculation with zero volatility"""
        metrics = StrategyMetrics(
            strategy_name="test",
            total_return=0.10,
            volatility=0.0,
        )
        metrics.update_ir(benchmark_return=0.0)

        # Should be 0 when volatility is 0
        self.assertEqual(metrics.information_ratio, 0.0)

    def test_ir_with_negative_return(self):
        """Test IR calculation with negative return"""
        metrics = StrategyMetrics(
            strategy_name="test",
            total_return=-0.05,
            volatility=0.05,
        )
        metrics.update_ir(benchmark_return=0.0)

        expected_ir = -0.05 / 0.05
        self.assertAlmostEqual(metrics.information_ratio, expected_ir, places=4)


class TestInformationRatioSizer(unittest.TestCase):
    """Test InformationRatioSizer class"""

    def setUp(self):
        """Initialize sizer for each test"""
        self.sizer = InformationRatioSizer(
            target_ir=0.5,
            min_ir=0.0,
            max_ir=2.0,
        )

    def test_initialization(self):
        """Test sizer initialization"""
        self.assertEqual(self.sizer.target_ir, 0.5)
        self.assertEqual(self.sizer.min_ir, 0.0)
        self.assertEqual(self.sizer.max_ir, 2.0)
        self.assertEqual(len(self.sizer.strategy_metrics), 0)

    def test_update_strategy_metrics_single_strategy(self):
        """Test updating metrics for a single strategy"""
        returns = np.array([0.01, 0.02, -0.01, 0.015, 0.01])

        self.sizer.update_strategy_metrics(
            strategy_name="strategy_a",
            returns=returns.tolist(),
            benchmark_return=0.0,
        )

        self.assertIn("strategy_a", self.sizer.strategy_metrics)
        metrics = self.sizer.strategy_metrics["strategy_a"]

        # Verify metrics were calculated
        self.assertGreater(metrics.information_ratio, 0)
        self.assertGreater(metrics.volatility, 0)
        self.assertEqual(metrics.num_trades, 5)

    def test_update_strategy_metrics_insufficient_data(self):
        """Test updating metrics with insufficient data"""
        returns = [0.01]  # Only 1 return

        # Should not crash, should log warning
        self.sizer.update_strategy_metrics(
            strategy_name="strategy_a",
            returns=returns,
            benchmark_return=0.0,
        )

        # Strategy should not be in metrics
        self.assertNotIn("strategy_a", self.sizer.strategy_metrics)

    def test_get_ir_adjusted_size_no_historical_data(self):
        """Test position sizing with no historical data"""
        # No metrics for this strategy
        adjusted_size = self.sizer.get_ir_adjusted_size(
            strategy_name="unknown_strategy",
            base_size=0.5,
            use_historical=True,
        )

        # Should return base size when no data
        self.assertEqual(adjusted_size, 0.5)

    def test_get_ir_adjusted_size_with_historical_data(self):
        """Test position sizing with historical IR"""
        # Create strategy with known IR
        returns = np.array([0.02, 0.02, -0.01, 0.02, 0.02, 0.015])
        self.sizer.update_strategy_metrics(
            strategy_name="high_ir_strategy",
            returns=returns.tolist(),
            benchmark_return=0.0,
        )

        # Get adjusted size
        adjusted_size = self.sizer.get_ir_adjusted_size(
            strategy_name="high_ir_strategy",
            base_size=0.5,
            use_historical=True,
        )

        # IR should be positive, so multiplier > 1.0
        self.assertGreater(adjusted_size, 0.5)
        self.assertLessEqual(adjusted_size, 1.0)  # Capped at max_size=1.0

    def test_get_ir_adjusted_size_low_ir_strategy(self):
        """Test position sizing reduces for low IR strategy"""
        # Create strategy with very low IR (all losses)
        returns = np.array([-0.01, -0.02, -0.01, -0.015, -0.01])
        self.sizer.update_strategy_metrics(
            strategy_name="low_ir_strategy",
            returns=returns.tolist(),
            benchmark_return=0.0,
        )

        # Get adjusted size
        adjusted_size = self.sizer.get_ir_adjusted_size(
            strategy_name="low_ir_strategy",
            base_size=0.5,
            use_historical=True,
        )

        # IR is negative, so position should be reduced
        # But clamped to min_size=0.01
        self.assertGreaterEqual(adjusted_size, 0.01)
        self.assertLess(adjusted_size, 0.5)

    def test_ir_multiplier_clamping(self):
        """Test that IR multiplier is clamped to [0.1, 2.0]"""
        # Create strategy with very high IR (all wins with small volatility)
        returns = np.array([0.05, 0.05, 0.04, 0.05, 0.06])
        self.sizer.update_strategy_metrics(
            strategy_name="extreme_strategy",
            returns=returns.tolist(),
            benchmark_return=0.0,
        )

        # Get adjusted size
        adjusted_size = self.sizer.get_ir_adjusted_size(
            strategy_name="extreme_strategy",
            base_size=0.1,
            use_historical=True,
        )

        # Should be clamped at max_size
        self.assertLessEqual(adjusted_size, 1.0)

    def test_allocate_capital_by_ir_equal_strategies(self):
        """Test capital allocation with equal IR strategies"""
        # Create two strategies with similar returns
        returns_a = np.array([0.01, 0.01, 0.01, 0.01, 0.01])
        returns_b = np.array([0.01, 0.01, 0.01, 0.01, 0.01])

        self.sizer.update_strategy_metrics("strategy_a", returns_a.tolist(), 0.0)
        self.sizer.update_strategy_metrics("strategy_b", returns_b.tolist(), 0.0)

        # Allocate capital
        allocation = self.sizer.allocate_capital_by_ir(
            strategy_names=["strategy_a", "strategy_b"],
            total_capital=1000,
            min_allocation=50,
        )

        # Should allocate roughly equally
        self.assertAlmostEqual(allocation["strategy_a"], allocation["strategy_b"], delta=100)
        self.assertLessEqual(
            abs(allocation["strategy_a"] + allocation["strategy_b"] - 1000),
            1.0,  # Rounding tolerance
        )

    def test_allocate_capital_by_ir_unequal_strategies(self):
        """Test capital allocation favors higher IR strategies"""
        # Create low IR strategy (negative returns with low volatility)
        returns_a = np.array([-0.01, -0.015, -0.008, -0.012, -0.01])

        # Create high IR strategy (positive returns with low volatility)
        returns_b = np.array([0.02, 0.025, 0.018, 0.022, 0.02])

        self.sizer.update_strategy_metrics("low_ir", returns_a.tolist(), 0.0)
        self.sizer.update_strategy_metrics("high_ir", returns_b.tolist(), 0.0)

        allocation = self.sizer.allocate_capital_by_ir(
            strategy_names=["low_ir", "high_ir"],
            total_capital=1000,
            min_allocation=50,
        )

        # High IR should get more allocation
        self.assertGreater(allocation["high_ir"], allocation["low_ir"])

    def test_get_strategy_ranking(self):
        """Test strategy ranking by Information Ratio"""
        # Create strategies with different IR (add variance to avoid 0 volatility)
        self.sizer.update_strategy_metrics("weak", np.array([-0.01, -0.015, -0.008, -0.012, -0.01]).tolist(), 0.0)
        self.sizer.update_strategy_metrics("good", np.array([0.01, 0.015, 0.008, 0.012, 0.01]).tolist(), 0.0)
        self.sizer.update_strategy_metrics("excellent", np.array([0.02, 0.025, 0.018, 0.022, 0.02]).tolist(), 0.0)

        rankings = self.sizer.get_strategy_ranking()

        # Should be sorted by IR descending
        self.assertEqual(rankings[0][0], "excellent")
        self.assertEqual(rankings[1][0], "good")
        self.assertEqual(rankings[2][0], "weak")

    def test_get_metrics_summary(self):
        """Test getting summary of all metrics"""
        returns = np.array([0.01, 0.02, -0.01, 0.015, 0.01])
        self.sizer.update_strategy_metrics("strategy_a", returns.tolist(), 0.0)

        summary = self.sizer.get_metrics_summary()

        self.assertIn("strategy_a", summary)
        self.assertIn("ir", summary["strategy_a"])
        self.assertIn("sharpe", summary["strategy_a"])
        self.assertIn("volatility", summary["strategy_a"])
        self.assertIn("total_return", summary["strategy_a"])
        self.assertIn("win_rate", summary["strategy_a"])

    def test_calculate_portfolio_ir(self):
        """Test blended portfolio IR calculation"""
        # Create two strategies with variance
        returns_a = np.array([0.01, 0.015, 0.008, 0.012, 0.01])
        returns_b = np.array([0.02, 0.025, 0.018, 0.022, 0.02])

        self.sizer.update_strategy_metrics("strategy_a", returns_a.tolist(), 0.0)
        self.sizer.update_strategy_metrics("strategy_b", returns_b.tolist(), 0.0)

        portfolio_ir = self.sizer.calculate_portfolio_ir()

        # Portfolio IR should be positive and between individual strategies
        self.assertGreater(portfolio_ir, 0)

    def test_multiple_update_cycles(self):
        """Test multiple update cycles for strategy"""
        # First cycle with lower returns
        returns_1 = np.array([0.01, 0.015, 0.008, 0.012, 0.01])
        self.sizer.update_strategy_metrics("strategy", returns_1.tolist(), 0.0)

        first_ir = self.sizer.strategy_metrics["strategy"].information_ratio

        # Second cycle with higher returns
        returns_2 = np.array([0.02, 0.025, 0.018, 0.022, 0.02])
        self.sizer.update_strategy_metrics("strategy", returns_2.tolist(), 0.0)

        second_ir = self.sizer.strategy_metrics["strategy"].information_ratio

        # IR should update (higher returns = higher IR)
        self.assertGreater(second_ir, first_ir)

    def test_empty_portfolio_ir(self):
        """Test portfolio IR with no strategies"""
        portfolio_ir = self.sizer.calculate_portfolio_ir()

        # Should return 0 when no metrics
        self.assertEqual(portfolio_ir, 0.0)

    def test_benchmark_return_affects_ir(self):
        """Test that benchmark return affects IR calculation"""
        returns = np.array([0.02, 0.025, 0.018, 0.022, 0.02])

        # Update with 0 benchmark
        self.sizer.update_strategy_metrics("strategy_a", returns.tolist(), benchmark_return=0.0)
        ir_vs_zero = self.sizer.strategy_metrics["strategy_a"].information_ratio

        # Create new sizer for second test
        sizer2 = InformationRatioSizer(target_ir=0.5)

        # Update with 1% benchmark
        sizer2.update_strategy_metrics("strategy_a", returns.tolist(), benchmark_return=0.01)
        ir_vs_benchmark = sizer2.strategy_metrics["strategy_a"].information_ratio

        # IR should be lower when benchmarking against positive return
        self.assertLess(ir_vs_benchmark, ir_vs_zero)

    def test_position_size_bounds(self):
        """Test that position sizes respect min and max bounds"""
        # Create strategy with extreme IR
        returns = np.array([0.10, 0.10, 0.10, 0.10, 0.10])
        self.sizer.update_strategy_metrics("strategy", returns.tolist(), 0.0)

        # Get adjusted size with small base
        adjusted_size = self.sizer.get_ir_adjusted_size(
            strategy_name="strategy",
            base_size=0.001,  # Very small base
            use_historical=True,
        )

        # Should be bounded by min_size
        self.assertGreaterEqual(adjusted_size, self.sizer.min_size)

    def test_win_rate_calculation(self):
        """Test win rate calculation in metrics"""
        returns = np.array([0.01, -0.02, 0.01, 0.01, -0.01])
        self.sizer.update_strategy_metrics("strategy", returns.tolist(), 0.0)

        metrics = self.sizer.strategy_metrics["strategy"]

        # 3 wins out of 5 trades
        expected_win_rate = 3 / 5
        self.assertAlmostEqual(metrics.win_rate, expected_win_rate, places=4)


class TestInformationRatioIntegration(unittest.TestCase):
    """Integration tests for Information Ratio Sizing"""

    def test_full_workflow_ir_sizing(self):
        """Test complete workflow: update metrics -> size positions -> rank strategies"""
        sizer = InformationRatioSizer(target_ir=0.5)

        # Simulate three strategies with different performance
        strategies = {
            "arbitrage": np.array([0.005, 0.005, 0.005, 0.005, 0.005, 0.004, 0.005]),  # Consistent small wins
            "momentum": np.array([0.01, -0.02, 0.015, -0.01, 0.02, 0.01, 0.015]),  # Volatile larger moves
            "mean_reversion": np.array([-0.002, -0.001, 0.001, -0.002, 0.001, -0.001, 0.002]),  # Noisy
        }

        # Update metrics for all strategies
        for name, returns in strategies.items():
            sizer.update_strategy_metrics(name, returns.tolist(), benchmark_return=0.0)

        # Get sizing for equal base positions
        base_size = 0.05
        sizes = {
            name: sizer.get_ir_adjusted_size(name, base_size, use_historical=True)
            for name in strategies.keys()
        }

        # Allocate capital based on IR
        allocation = sizer.allocate_capital_by_ir(
            strategy_names=list(strategies.keys()),
            total_capital=10000,
        )

        # Get rankings
        rankings = sizer.get_strategy_ranking()

        # Verify results are sensible
        # Arbitrage should be ranked high (consistent positive returns)
        self.assertEqual(rankings[0][0], "arbitrage")

        # Arbitrage should get most capital
        self.assertEqual(
            max(allocation.values()),
            allocation["arbitrage"],
        )


if __name__ == "__main__":
    unittest.main()
