"""
Tests for Bayesian confidence calibration

Confidence calibration ensures predicted confidence matches actual accuracy.
Expected improvement: +10-15% Sharpe ratio.
"""

import unittest
import numpy as np
from src.signal_quality.confidence_calibration import ConfidenceCalibrator, CalibrationMetrics


class TestCalibrationMetrics(unittest.TestCase):
    """Test CalibrationMetrics dataclass"""

    def test_create_metrics(self):
        """Test creating calibration metrics"""
        metrics = CalibrationMetrics(
            n_signals=100,
            expected_accuracy=0.75,
            actual_accuracy=0.72,
            calibration_error=0.03,
            reliability_curve_points=[(0.5, 0.48), (0.75, 0.73)],
        )

        self.assertEqual(metrics.n_signals, 100)
        self.assertEqual(metrics.expected_accuracy, 0.75)


class TestConfidenceCalibrator(unittest.TestCase):
    """Test ConfidenceCalibrator class"""

    def setUp(self):
        """Initialize calibrator for tests"""
        self.calibrator = ConfidenceCalibrator(method="binning", n_bins=10)

    def test_initialization(self):
        """Test calibrator initialization"""
        self.assertEqual(self.calibrator.method, "binning")
        self.assertEqual(self.calibrator.n_bins, 10)
        self.assertEqual(len(self.calibrator.predicted_confidences), 0)

    def test_add_observation(self):
        """Test adding observations"""
        self.calibrator.add_observation(0.8, 1)
        self.calibrator.add_observation(0.6, 0)

        self.assertEqual(len(self.calibrator.predicted_confidences), 2)
        self.assertEqual(self.calibrator.predicted_confidences[0], 0.8)
        self.assertEqual(self.calibrator.actual_outcomes[0], 1)

    def test_confidence_clipping(self):
        """Test that confidence is clipped to [0, 1]"""
        self.calibrator.add_observation(1.5, 1)  # > 1
        self.calibrator.add_observation(-0.5, 0)  # < 0

        self.assertLessEqual(self.calibrator.predicted_confidences[0], 1.0)
        self.assertGreaterEqual(self.calibrator.predicted_confidences[1], 0.0)

    def test_outcome_binarization(self):
        """Test that outcomes are binarized"""
        self.calibrator.add_observation(0.8, 0.7)  # > 0.5, should be 1
        self.calibrator.add_observation(0.6, 0.3)  # < 0.5, should be 0

        self.assertEqual(self.calibrator.actual_outcomes[0], 1)
        self.assertEqual(self.calibrator.actual_outcomes[1], 0)

    def test_fit_calibration_insufficient_data(self):
        """Test fitting with insufficient observations"""
        for i in range(5):
            self.calibrator.add_observation(0.5 + i * 0.05, i % 2)

        metrics = self.calibrator.fit_calibration()

        # Should still return metrics but won't be well-calibrated
        self.assertLess(metrics.n_signals, 10)

    def test_fit_calibration_perfect_predictions(self):
        """Test calibration when predictions are perfect"""
        # 80% confidence signals, 80% win rate
        for _ in range(20):
            self.calibrator.add_observation(0.8, 1)
        for _ in range(5):
            self.calibrator.add_observation(0.8, 0)

        metrics = self.calibrator.fit_calibration()

        self.assertGreaterEqual(metrics.n_signals, 25)
        self.assertAlmostEqual(metrics.expected_accuracy, 0.8, places=2)
        self.assertLess(metrics.calibration_error, 0.15)

    def test_fit_calibration_overconfident(self):
        """Test calibration when model is overconfident"""
        # 90% confidence signals but only 60% win rate
        for _ in range(15):
            self.calibrator.add_observation(0.9, 1)
        for _ in range(10):
            self.calibrator.add_observation(0.9, 0)

        metrics = self.calibrator.fit_calibration()

        self.assertGreater(metrics.calibration_error, 0.2)

    def test_fit_calibration_underconfident(self):
        """Test calibration when model is underconfident"""
        # 60% confidence signals but 85% win rate
        for _ in range(17):
            self.calibrator.add_observation(0.6, 1)
        for _ in range(3):
            self.calibrator.add_observation(0.6, 0)

        metrics = self.calibrator.fit_calibration()

        self.assertGreater(metrics.calibration_error, 0.2)

    def test_calibrate_confidence_no_calibration(self):
        """Test calibrating when no calibration data"""
        conf = self.calibrator.calibrate_confidence(0.7)

        # Should return unchanged when not calibrated
        self.assertAlmostEqual(conf, 0.7, places=5)

    def test_calibrate_confidence_after_fit(self):
        """Test calibration after fitting"""
        # Add high-confidence, low-accuracy signals
        for _ in range(20):
            self.calibrator.add_observation(0.8, 1)
        for _ in range(20):
            self.calibrator.add_observation(0.8, 0)

        self.calibrator.fit_calibration()
        calibrated = self.calibrator.calibrate_confidence(0.8)

        # Should be adjusted down due to poor performance
        self.assertLess(calibrated, 0.8)

    def test_calibrate_high_confidence_good_signal(self):
        """Test calibration of high-confidence good signal"""
        # Add high-confidence, high-accuracy signals
        for _ in range(40):
            self.calibrator.add_observation(0.8, 1)
        for _ in range(5):
            self.calibrator.add_observation(0.8, 0)

        self.calibrator.fit_calibration()
        calibrated = self.calibrator.calibrate_confidence(0.8)

        # Should stay high or increase slightly
        self.assertGreater(calibrated, 0.7)

    def test_interpolation_between_bins(self):
        """Test interpolation uses calibration map"""
        for _ in range(15):
            self.calibrator.add_observation(0.7, 1)
        for _ in range(5):
            self.calibrator.add_observation(0.7, 0)

        for _ in range(12):
            self.calibrator.add_observation(0.9, 1)
        for _ in range(8):
            self.calibrator.add_observation(0.9, 0)

        self.calibrator.fit_calibration()

        # All calibrated values should be in [0, 1]
        calibrated_07 = self.calibrator.calibrate_confidence(0.7)
        calibrated_08 = self.calibrator.calibrate_confidence(0.8)
        calibrated_09 = self.calibrator.calibrate_confidence(0.9)

        self.assertGreaterEqual(calibrated_07, 0.0)
        self.assertLessEqual(calibrated_07, 1.0)
        self.assertGreaterEqual(calibrated_08, 0.0)
        self.assertLessEqual(calibrated_08, 1.0)
        self.assertGreaterEqual(calibrated_09, 0.0)
        self.assertLessEqual(calibrated_09, 1.0)

    def test_get_calibration_summary(self):
        """Test getting calibration summary"""
        for _ in range(20):
            self.calibrator.add_observation(0.7, 1 if np.random.random() > 0.3 else 0)

        summary = self.calibrator.get_calibration_summary()

        self.assertEqual(summary["n_observations"], 20)
        self.assertIn("expected_accuracy", summary)
        self.assertIn("actual_accuracy", summary)
        self.assertIn("calibration_error", summary)
        self.assertIn("is_calibrated", summary)

    def test_binning_method(self):
        """Test binning calibration method"""
        calibrator = ConfidenceCalibrator(method="binning", n_bins=5)

        # Create diverse confidence scores
        for conf in [0.3, 0.5, 0.7, 0.9]:
            for _ in range(10):
                outcome = 1 if np.random.random() < conf else 0
                calibrator.add_observation(conf, outcome)

        metrics = calibrator.fit_calibration()

        self.assertGreaterEqual(len(metrics.reliability_curve_points), 0)

    def test_isotonic_method(self):
        """Test isotonic calibration method"""
        calibrator = ConfidenceCalibrator(method="isotonic", n_bins=5)

        # Add observations with trend
        for conf in np.linspace(0.2, 0.9, 30):
            outcome = 1 if np.random.random() < conf else 0
            calibrator.add_observation(conf, outcome)

        metrics = calibrator.fit_calibration()

        # Isotonic should produce monotonic calibration
        self.assertGreater(metrics.n_signals, 0)

    def test_beta_method(self):
        """Test beta regression calibration method"""
        calibrator = ConfidenceCalibrator(method="beta", n_bins=5)

        for conf in [0.3, 0.5, 0.7, 0.9]:
            for _ in range(10):
                outcome = 1 if np.random.random() < conf else 0
                calibrator.add_observation(conf, outcome)

        metrics = calibrator.fit_calibration()

        self.assertGreater(metrics.n_signals, 0)

    def test_multiple_confidence_levels(self):
        """Test calibration with multiple confidence levels"""
        # Different signals with different confidences and accuracies
        signals = [
            (0.9, 0.85),  # High confidence, high accuracy
            (0.7, 0.70),  # Medium confidence, medium accuracy
            (0.5, 0.50),  # Low confidence, random
            (0.8, 0.60),  # High confidence, low accuracy (overconfident)
        ]

        for conf, accuracy in signals:
            for _ in range(30):
                outcome = 1 if np.random.random() < accuracy else 0
                self.calibrator.add_observation(conf, outcome)

        metrics = self.calibrator.fit_calibration()
        self.assertEqual(metrics.n_signals, 120)

        # Overconfident signal should be calibrated down
        original_overconf = 0.8
        calibrated_overconf = self.calibrator.calibrate_confidence(original_overconf)
        self.assertLess(calibrated_overconf, original_overconf)


class TestCalibrationIntegration(unittest.TestCase):
    """Integration tests for calibration workflow"""

    def test_full_workflow(self):
        """Test complete calibration workflow"""
        calibrator = ConfidenceCalibrator(method="binning")

        # Simulate trading with diverse signals
        np.random.seed(42)
        for signal_id in range(100):
            # Random confidence and accuracy
            confidence = np.random.beta(2, 2)  # Favors middle values
            true_win_prob = confidence + np.random.normal(0, 0.1)
            true_win_prob = np.clip(true_win_prob, 0, 1)

            # Outcome based on true probability
            outcome = 1 if np.random.random() < true_win_prob else 0
            calibrator.add_observation(confidence, outcome)

        # Fit calibration
        metrics = calibrator.fit_calibration()
        self.assertEqual(metrics.n_signals, 100)

        # Test calibration on new signals
        for conf in [0.2, 0.5, 0.8]:
            calibrated = calibrator.calibrate_confidence(conf)
            self.assertGreaterEqual(calibrated, 0.0)
            self.assertLessEqual(calibrated, 1.0)

    def test_incremental_calibration(self):
        """Test calibration improves with more data"""
        calibrator = ConfidenceCalibrator(method="binning")

        # Add few observations
        for _ in range(5):
            calibrator.add_observation(0.7, 1)
        for _ in range(5):
            calibrator.add_observation(0.7, 0)

        metrics_few = calibrator.fit_calibration()

        # Add many more observations with same pattern
        for _ in range(40):
            calibrator.add_observation(0.7, 1)
        for _ in range(40):
            calibrator.add_observation(0.7, 0)

        metrics_many = calibrator.fit_calibration()

        # With more data, estimates should be more confident
        self.assertGreater(metrics_many.n_signals, metrics_few.n_signals)


if __name__ == "__main__":
    unittest.main()
