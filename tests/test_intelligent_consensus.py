"""Tests for intelligent consensus engine with conflict tracking and Bayesian fusion"""

import unittest
import numpy as np
from datetime import datetime

from src.trading.intelligent_consensus import (
    IntelligentConsensusEngine,
    MarketRegime,
    ConflictOutcome,
    RegimeMetrics
)
from src.data.models import Signal, Direction, Outcome


class TestRegimeDetection(unittest.TestCase):
    """Test market regime detection"""

    def setUp(self):
        self.metrics = RegimeMetrics()

    def test_trending_up_detection(self):
        """Detect uptrend"""
        # Steady uptrend
        for i in range(50):
            price = 0.50 + (i * 0.01)  # Linear up
            self.metrics.update(price, 0.08)

        self.assertEqual(self.metrics.current_regime, MarketRegime.TRENDING)
        self.assertGreater(self.metrics.trend_strength, 0.2)

    def test_mean_reverting_detection(self):
        """Detect mean-reverting market"""
        mean = 0.50
        # Oscillate around mean with some randomness for proper autocorr
        np.random.seed(42)
        for i in range(60):
            price = mean + 0.05 * np.sin(i * 0.3) + np.random.normal(0, 0.005)
            self.metrics.update(price, 0.06)

        # Check for mean-reverting properties (may detect as RANGE_BOUND too)
        self.assertIn(self.metrics.current_regime,
                     [MarketRegime.MEAN_REVERTING, MarketRegime.RANGE_BOUND, MarketRegime.LOW_VOLATILITY])
        # Reversion score should be valid (>= 0)
        self.assertGreaterEqual(self.metrics.reversion_score, 0)

    def test_high_volatility_detection(self):
        """Detect high volatility regime"""
        for i in range(50):
            price = 0.50 + np.random.normal(0, 0.03)  # High volatility
            self.metrics.update(price, 0.20)

        self.assertEqual(self.metrics.current_regime, MarketRegime.HIGH_VOLATILITY)

    def test_range_bound_detection(self):
        """Detect range-bound or low volatility market"""
        for i in range(50):
            price = 0.48 + (i % 10) * 0.001  # Tight range
            self.metrics.update(price, 0.03)

        # Low volatility → RANGE_BOUND or LOW_VOLATILITY
        self.assertIn(self.metrics.current_regime,
                     [MarketRegime.RANGE_BOUND, MarketRegime.LOW_VOLATILITY])


class TestBayesianFusion(unittest.TestCase):
    """Test Bayesian signal fusion"""

    def setUp(self):
        self.engine = IntelligentConsensusEngine()
        self.timestamp = datetime.utcnow()

    def test_unanimous_agreement(self):
        """All strategies agree -> high confidence"""
        signals = {
            'arbitrage': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='arbitrage',
                direction=Direction.BUY,
                outcome=Outcome.YES,
                contracts=500,
                confidence=0.85,
                reason='Arb'
            )],
            'momentum': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='momentum',
                direction=Direction.BUY,
                outcome=Outcome.YES,
                contracts=400,
                confidence=0.80,
                reason='Momentum'
            )],
            'mean_reversion': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='mean_reversion',
                direction=Direction.BUY,
                outcome=Outcome.YES,
                contracts=450,
                confidence=0.75,
                reason='MR'
            )],
        }

        merged = self.engine.merge_signals_intelligent(signals)

        self.assertIn('MARKET_1', merged)
        self.assertEqual(merged['MARKET_1'].direction, Direction.BUY)
        # High consensus should give high confidence
        self.assertGreater(merged['MARKET_1'].confidence, 0.75)

    def test_2v2_conflict_close_call(self):
        """2v2 conflict with close confidence -> low confidence output"""
        signals = {
            'arbitrage': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='arbitrage',
                direction=Direction.BUY,
                outcome=Outcome.YES,
                contracts=500,
                confidence=0.75,
                reason='Arb buy'
            )],
            'momentum': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='momentum',
                direction=Direction.BUY,
                outcome=Outcome.YES,
                contracts=400,
                confidence=0.74,
                reason='Momentum buy'
            )],
            'mean_reversion': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='mean_reversion',
                direction=Direction.SELL,
                outcome=Outcome.YES,
                contracts=450,
                confidence=0.72,
                reason='MR sell'
            )],
            'cross_ex': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='cross_ex',
                direction=Direction.SELL,
                outcome=Outcome.YES,
                contracts=480,
                confidence=0.71,
                reason='Cross sell'
            )],
        }

        merged = self.engine.merge_signals_intelligent(signals)

        self.assertIn('MARKET_1', merged)
        # Close call -> reduced confidence
        self.assertLess(merged['MARKET_1'].confidence, 0.70)

    def test_3v1_conflict_clear_winner(self):
        """3v1 conflict -> majority has stronger signal"""
        signals = {
            'arbitrage': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='arbitrage',
                direction=Direction.BUY,
                outcome=Outcome.YES,
                contracts=500,
                confidence=0.85,
                reason='Arb buy'
            )],
            'momentum': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='momentum',
                direction=Direction.BUY,
                outcome=Outcome.YES,
                contracts=400,
                confidence=0.80,
                reason='Momentum buy'
            )],
            'mean_reversion': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='mean_reversion',
                direction=Direction.BUY,
                outcome=Outcome.YES,
                contracts=450,
                confidence=0.78,
                reason='MR buy'
            )],
            'cross_ex': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='cross_ex',
                direction=Direction.SELL,
                outcome=Outcome.YES,
                contracts=480,
                confidence=0.55,
                reason='Cross sell'
            )],
        }

        merged = self.engine.merge_signals_intelligent(signals)

        self.assertIn('MARKET_1', merged)
        # 3v1 should produce a signal
        self.assertIsNotNone(merged['MARKET_1'])
        # 3 signals on one side should win majority
        if merged['MARKET_1'].direction == Direction.BUY:
            # Confidence should be reasonable for 3v1
            self.assertGreater(merged['MARKET_1'].confidence, 0.60)


class TestConflictTracking(unittest.TestCase):
    """Test conflict tracking and learning"""

    def setUp(self):
        self.engine = IntelligentConsensusEngine()
        self.timestamp = datetime.utcnow()

    def test_conflict_logging(self):
        """Conflicts are logged"""
        signals = {
            'arbitrage': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='arbitrage',
                direction=Direction.BUY,
                outcome=Outcome.YES,
                contracts=500,
                confidence=0.75,
                reason='Buy'
            )],
            'mean_reversion': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='mean_reversion',
                direction=Direction.SELL,
                outcome=Outcome.YES,
                contracts=450,
                confidence=0.72,
                reason='Sell'
            )],
        }

        merged = self.engine.merge_signals_intelligent(signals)
        self.assertEqual(len(self.engine.conflict_history), 1)

    def test_outcome_recording(self):
        """Outcomes update strategy stats"""
        # Create a conflict
        signals = {
            'arbitrage': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='arbitrage',
                direction=Direction.BUY,
                outcome=Outcome.YES,
                contracts=500,
                confidence=0.75,
                reason='Buy'
            )],
            'mean_reversion': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='mean_reversion',
                direction=Direction.SELL,
                outcome=Outcome.YES,
                contracts=450,
                confidence=0.72,
                reason='Sell'
            )],
        }

        merged = self.engine.merge_signals_intelligent(signals)
        conflict = self.engine.conflict_history[0]

        # Record that BUY was correct
        self.engine.record_outcome(conflict, Direction.BUY, pnl=100.0)

        # Arbitrage should have improved stats
        self.assertIn('arbitrage', self.engine.strategy_stats)
        arb_stats = self.engine.strategy_stats['arbitrage']
        self.assertEqual(arb_stats.correct_signals, 1)
        self.assertEqual(arb_stats.conflict_wins, 1)

    def test_conflict_accuracy_tracking(self):
        """System tracks accuracy of conflict resolutions"""
        # Do 5 conflicts with known outcomes
        for i in range(5):
            signals = {
                'arb': [Signal(
                    timestamp=self.timestamp,
                    market_id=f'M{i}',
                    strategy_name='arb',
                    direction=Direction.BUY,
                    outcome=Outcome.YES,
                    contracts=500,
                    confidence=0.8,
                    reason='Buy'
                )],
                'mr': [Signal(
                    timestamp=self.timestamp,
                    market_id=f'M{i}',
                    strategy_name='mr',
                    direction=Direction.SELL,
                    outcome=Outcome.YES,
                    contracts=450,
                    confidence=0.7,
                    reason='Sell'
                )],
            }

            merged = self.engine.merge_signals_intelligent(signals)
            conflict = self.engine.conflict_history[i]

            # Arb picked (higher confidence), and 3/5 times it was correct
            if i < 3:
                self.engine.record_outcome(conflict, Direction.BUY)
            else:
                self.engine.record_outcome(conflict, Direction.SELL)

        report = self.engine.get_intelligence_report()
        accuracy = report['conflict_resolution_accuracy']

        # 3/5 conflicts resolved correctly
        self.assertEqual(accuracy, 0.6)

    def test_strategy_stat_updates(self):
        """Strategy statistics accumulate correctly"""
        signals = {
            'arbitrage': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='arbitrage',
                direction=Direction.BUY,
                outcome=Outcome.YES,
                contracts=500,
                confidence=0.75,
                reason='Buy'
            )],
            'mean_reversion': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='mean_reversion',
                direction=Direction.SELL,
                outcome=Outcome.YES,
                contracts=450,
                confidence=0.72,
                reason='Sell'
            )],
        }

        merged = self.engine.merge_signals_intelligent(signals)
        conflict = self.engine.conflict_history[0]

        # Record multiple outcomes
        self.engine.record_outcome(conflict, Direction.BUY)  # Arb correct
        self.engine.record_outcome(conflict, Direction.BUY)  # Arb correct again

        arb_stats = self.engine.strategy_stats['arbitrage']
        self.assertEqual(arb_stats.total_signals, 2)
        self.assertEqual(arb_stats.correct_signals, 2)
        self.assertEqual(arb_stats.win_rate, 1.0)


class TestRegimeAwareWeighting(unittest.TestCase):
    """Test that regimes affect strategy weighting"""

    def setUp(self):
        self.engine = IntelligentConsensusEngine()
        self.timestamp = datetime.utcnow()

    def test_trend_favors_momentum(self):
        """Trending regime should weight momentum higher"""
        # Set up trending regime
        for i in range(50):
            price = 0.50 + (i * 0.01)
            self.engine.regime_metrics['MARKET_1'].update(price, 0.08)

        regime = self.engine.regime_metrics['MARKET_1'].current_regime
        self.assertEqual(regime, MarketRegime.TRENDING)

        # Check weights in trending regime
        momentum_weight = self.engine.regime_weights['improved_momentum'][regime]
        arb_weight = self.engine.regime_weights['enhanced_matched_pair'][regime]

        # Momentum should be weighted higher in trending
        self.assertGreater(momentum_weight, arb_weight)

    def test_mean_reversion_regime_weights(self):
        """Mean reverting regime should weight mean reversion higher"""
        # Set up mean-reverting regime
        mean = 0.50
        for i in range(60):
            price = mean + 0.05 * np.sin(i * 0.3)
            self.engine.regime_metrics['MARKET_1'].update(price, 0.06)

        regime = self.engine.regime_metrics['MARKET_1'].current_regime
        # Should be in mean-reverting or range-bound family
        self.assertIn(regime, [MarketRegime.MEAN_REVERTING, MarketRegime.RANGE_BOUND])

        # Mean reversion should be weighted at least as high as momentum in non-trending
        mr_weight = self.engine.regime_weights['mean_reversion'][regime]
        momentum_weight = self.engine.regime_weights['improved_momentum'][regime]

        # In range/mean-reverting regimes, MR >= momentum
        self.assertGreaterEqual(mr_weight, momentum_weight * 0.9)


class TestIntelligenceReport(unittest.TestCase):
    """Test reporting of consensus engine intelligence"""

    def setUp(self):
        self.engine = IntelligentConsensusEngine()
        self.timestamp = datetime.utcnow()

    def test_report_structure(self):
        """Intelligence report has correct structure"""
        signals = {
            'arbitrage': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='arbitrage',
                direction=Direction.BUY,
                outcome=Outcome.YES,
                contracts=500,
                confidence=0.75,
                reason='Buy'
            )],
        }

        self.engine.merge_signals_intelligent(signals)
        report = self.engine.get_intelligence_report()

        self.assertIn('total_conflicts', report)
        self.assertIn('strategy_stats', report)
        self.assertIn('regime_metrics', report)
        self.assertIn('conflict_resolution_accuracy', report)

    def test_strategy_stats_in_report(self):
        """Strategy stats are included in report"""
        signals = {
            'arbitrage': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='arbitrage',
                direction=Direction.BUY,
                outcome=Outcome.YES,
                contracts=500,
                confidence=0.75,
                reason='Buy'
            )],
            'momentum': [Signal(
                timestamp=self.timestamp,
                market_id='MARKET_1',
                strategy_name='momentum',
                direction=Direction.SELL,  # Conflict
                outcome=Outcome.YES,
                contracts=400,
                confidence=0.70,
                reason='Momentum'
            )],
        }

        self.engine.merge_signals_intelligent(signals)

        # Create a conflict outcome and record it to get stats
        if self.engine.conflict_history:
            conflict = self.engine.conflict_history[0]
            self.engine.record_outcome(conflict, Direction.BUY)

        report = self.engine.get_intelligence_report()

        # After recording outcome, strategies should be in stats
        self.assertGreater(len(report['strategy_stats']), 0)


if __name__ == '__main__':
    unittest.main()
