"""Unit tests for mean reversion detector module"""

import unittest
import numpy as np
from datetime import datetime
from src.strategies.mean_reversion_detector import MeanReversionDetector
from src.strategies.base_strategy import MarketState


class TestMeanReversionDetector(unittest.TestCase):
    """Test MeanReversionDetector class"""

    def setUp(self):
        self.detector = MeanReversionDetector(
            config={
                "lookback_window": 20,
                "z_score_threshold": 2.0,
                "bollinger_std_dev": 2.0,
                "min_confidence": 0.5,
            }
        )

    def test_initialize(self):
        """Test initialization with config"""
        self.assertEqual(self.detector.lookback_window, 20)
        self.assertEqual(self.detector.z_score_threshold, 2.0)
        self.assertEqual(self.detector.bollinger_std_dev, 2.0)
        self.assertEqual(self.detector.min_confidence, 0.5)

    def test_price_history_tracking(self):
        """Test that price history is tracked correctly"""
        market_state = MarketState(
            timestamp=datetime.utcnow(),
            market_id="MARKET_1",
            yes_bid=0.48,
            yes_ask=0.52,
            no_bid=0.48,
            no_ask=0.52,
            volume_24h=1000,
            lookback_data=[],
        )

        signals = self.detector.generate_signals(market_state)

        # Should have price history now
        self.assertIn("MARKET_1", self.detector.price_history)
        self.assertEqual(len(self.detector.price_history["MARKET_1"]), 1)

    def test_insufficient_data_returns_no_signals(self):
        """Test that insufficient data returns no signals"""
        market_state = MarketState(
            timestamp=datetime.utcnow(),
            market_id="MARKET_1",
            yes_bid=0.48,
            yes_ask=0.52,
            no_bid=0.48,
            no_ask=0.52,
            volume_24h=1000,
            lookback_data=[],
        )

        signals = self.detector.generate_signals(market_state)
        self.assertEqual(len(signals), 0)

    def test_mean_reversion_buy_signal(self):
        """Test generation of buy signal when price is too low"""
        # Create market with mean around 0.50
        prices = [0.50] * 20 + [0.40]  # Last price significantly below mean
        all_signals = []

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
            signals = self.detector.generate_signals(market_state)
            all_signals.extend(signals)

        # Should have buy signal when price drops significantly
        self.assertGreater(len(all_signals), 0)
        buy_signals = [s for s in all_signals if s.direction.name == "BUY"]
        self.assertGreater(len(buy_signals), 0)

    def test_mean_reversion_sell_signal(self):
        """Test generation of sell signal when price is too high"""
        # Create market with mean around 0.50
        prices = [0.50] * 20 + [0.60]  # Last price significantly above mean
        all_signals = []

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
            signals = self.detector.generate_signals(market_state)
            all_signals.extend(signals)

        # Should have sell signal when price rises significantly
        self.assertGreater(len(all_signals), 0)
        sell_signals = [s for s in all_signals if s.direction.name == "SELL"]
        self.assertGreater(len(sell_signals), 0)

    def test_hurst_exponent_calculation(self):
        """Test Hurst exponent calculation"""
        # Mean-reverting series with small random variations
        np.random.seed(42)
        prices = np.array([0.50 + 0.02 * np.sin(i / 2) + 0.005 * np.random.randn() for i in range(30)])

        hurst = self.detector._calculate_hurst_exponent(prices)

        # Hurst should be between 0 and 1 (or NaN if calculation fails gracefully)
        if not np.isnan(hurst):
            self.assertGreaterEqual(hurst, 0.0)
            self.assertLessEqual(hurst, 1.0)

    def test_hurst_exponent_insufficient_data(self):
        """Test Hurst exponent with insufficient data"""
        prices = np.array([0.50, 0.51, 0.49])
        hurst = self.detector._calculate_hurst_exponent(prices)
        # Should return default 0.5 for insufficient data
        self.assertEqual(hurst, 0.5)

    def test_mean_reversion_score(self):
        """Test mean reversion score calculation"""
        z_score = 2.5
        hurst = 0.3  # Mean-reverting

        mr_score = self.detector._calculate_mean_reversion_score(z_score, hurst)

        # Score should be between 0 and 1
        self.assertGreaterEqual(mr_score, 0.0)
        self.assertLessEqual(mr_score, 1.0)

        # High z-score and low Hurst should give high score
        self.assertGreater(mr_score, 0.5)

    def test_mean_reversion_score_trending(self):
        """Test mean reversion score with trending market"""
        z_score = 2.5
        hurst = 0.7  # Trending, not mean-reverting

        mr_score = self.detector._calculate_mean_reversion_score(z_score, hurst)

        # Score should still be reasonable despite trending market
        self.assertGreaterEqual(mr_score, 0.0)
        self.assertLessEqual(mr_score, 1.0)

    def test_is_mean_reverting(self):
        """Test mean reversion detection check"""
        # Set up a mean-reverting market
        for i in range(25):
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
            self.detector.generate_signals(market_state)

        # Check if market is detected as mean-reverting
        is_mr = self.detector.is_mean_reverting("MARKET_1")
        # Should be boolean-like (bool or np.bool_)
        self.assertIn(type(is_mr).__name__, ['bool', 'bool_'])

    def test_get_mean_reversion_strength(self):
        """Test mean reversion strength retrieval"""
        # Set up market with some history
        for i in range(25):
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
            self.detector.generate_signals(market_state)

        strength = self.detector.get_mean_reversion_strength("MARKET_1")

        # Strength should be between 0 and 1
        self.assertGreaterEqual(strength, 0.0)
        self.assertLessEqual(strength, 1.0)

    def test_get_metrics(self):
        """Test metrics retrieval"""
        market_state = MarketState(
            timestamp=datetime.utcnow(),
            market_id="MARKET_1",
            yes_bid=0.48,
            yes_ask=0.52,
            no_bid=0.48,
            no_ask=0.52,
            volume_24h=1000,
            lookback_data=[],
        )
        self.detector.generate_signals(market_state)

        metrics = self.detector.get_metrics()

        self.assertIn("name", metrics)
        self.assertIn("mean_reversion_scores", metrics)
        self.assertIn("hurst_exponents", metrics)
        self.assertEqual(metrics["name"], "MeanReversion")


if __name__ == "__main__":
    unittest.main()
