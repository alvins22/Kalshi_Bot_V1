"""Quick tests for EVT and DCC"""
import unittest
import numpy as np
from src.risk.extreme_value_theory import ExtremeValueTheory
from src.risk.dynamic_correlation import DynamicConditionalCorrelation


class TestEVT(unittest.TestCase):
    def setUp(self):
        self.evt = ExtremeValueTheory(threshold_pct=90)

    def test_basic_var(self):
        """Test VaR calculation"""
        for _ in range(100):
            self.evt.add_return("TEST", np.random.normal(-0.01, 0.02))
        var = self.evt.get_var("TEST", 0.95)
        self.assertLess(var, 0.1)
        self.assertGreater(var, -0.1)

    def test_tail_risk_score(self):
        """Test tail risk scoring"""
        for _ in range(100):
            self.evt.add_return("TEST", np.random.normal(0, 0.01))
        score = self.evt.get_tail_risk_score("TEST")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_insufficient_data(self):
        """Test with insufficient data"""
        self.evt.add_return("TEST", 0.01)
        var = self.evt.get_var("TEST", 0.95)
        self.assertEqual(var, 0.05)  # Default


class TestDCC(unittest.TestCase):
    def setUp(self):
        self.dcc = DynamicConditionalCorrelation(alpha=0.05, beta=0.94)

    def test_add_returns(self):
        """Test adding returns"""
        self.dcc.add_returns({"M1": 0.01, "M2": 0.02})
        self.assertEqual(len(self.dcc.returns_history), 2)

    def test_update_dcc(self):
        """Test DCC update"""
        for _ in range(50):
            self.dcc.add_returns({
                "M1": np.random.normal(0, 0.01),
                "M2": np.random.normal(0, 0.01)
            })
        self.dcc.update_dcc()
        corr = self.dcc.get_correlation("M1", "M2")
        self.assertGreaterEqual(corr, -1.0)
        self.assertLessEqual(corr, 1.0)

    def test_stress_score(self):
        """Test correlation stress score"""
        for _ in range(50):
            self.dcc.add_returns({
                "M1": np.random.normal(0, 0.01),
                "M2": np.random.normal(0, 0.01)
            })
        self.dcc.update_dcc()
        stress = self.dcc.get_correlation_stress_score()
        self.assertGreaterEqual(stress, 0.0)
        self.assertLessEqual(stress, 1.0)


if __name__ == "__main__":
    unittest.main()
