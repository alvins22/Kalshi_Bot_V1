"""Tests for Kalman filter mean estimation"""
import unittest
import numpy as np
from src.strategies.kalman_filter_mean import KalmanFilterMeanEstimator


class TestKalmanFilter(unittest.TestCase):
    def setUp(self):
        self.kf = KalmanFilterMeanEstimator(
            process_variance=1e-4,
            observation_variance=1.0,
            initial_mean=0.5
        )

    def test_initialization(self):
        self.assertEqual(self.kf.Q, 1e-4)
        self.assertEqual(self.kf.R, 1.0)

    def test_single_update(self):
        mean, trend = self.kf.update("MARKET_1", 0.52)
        self.assertIsNotNone(mean)
        self.assertGreaterEqual(mean, 0.0)
        self.assertLessEqual(mean, 1.0)

    def test_converges_to_constant(self):
        """Filter should converge to constant price"""
        for _ in range(50):
            self.kf.update("TEST", 0.6)
        mean = self.kf.get_mean("TEST")
        self.assertGreater(mean, 0.55)
        self.assertLess(mean, 0.65)

    def test_z_score(self):
        for _ in range(10):
            self.kf.update("TEST", 0.5)
        z = self.kf.get_z_score("TEST", 0.5)
        self.assertLess(abs(z), 0.5)

    def test_confidence_increases(self):
        conf1 = self.kf.get_confidence("TEST")
        for _ in range(20):
            self.kf.update("TEST", 0.5)
        conf2 = self.kf.get_confidence("TEST")
        self.assertGreater(conf2, conf1)

    def test_multiple_markets(self):
        self.kf.update("M1", 0.4)
        self.kf.update("M2", 0.6)
        m1 = self.kf.get_mean("M1")
        m2 = self.kf.get_mean("M2")
        self.assertNotEqual(m1, m2)

    def test_reset(self):
        self.kf.update("TEST", 0.6)
        self.kf.reset("TEST")
        mean = self.kf.get_mean("TEST")
        self.assertEqual(mean, 0.5)

    def test_handles_trend(self):
        """Filter should adapt to price trends"""
        for i in range(30):
            price = 0.5 + i * 0.01  # Uptrend
            self.kf.update("TREND", price)
        mean = self.kf.get_mean("TREND")
        self.assertGreater(mean, 0.6)  # Should move toward higher prices


if __name__ == "__main__":
    unittest.main()
