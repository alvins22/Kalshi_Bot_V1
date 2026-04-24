"""Tests for signal profitability tracking"""

import pytest
from datetime import datetime, timedelta

from src.trading.signal_profitability import SignalProfitabilityTracker, SignalMetrics, StrategySignalStats
from src.data.models import Signal, Direction, Outcome


class TestSignalProfitabilityTracker:
    """Test signal profitability tracking"""

    def test_record_signal_creates_metrics(self):
        """Should create metrics when recording signal"""
        tracker = SignalProfitabilityTracker()

        signal = Signal(
            timestamp=datetime.utcnow(),
            market_id="TEST-001",
            strategy_name="TestStrategy",
            direction=Direction.BUY,
            outcome=Outcome.YES,
            contracts=100,
            confidence=0.75,
            estimated_price=0.55,
        )

        signal_id = tracker.record_signal(signal)

        assert signal_id is not None
        assert signal_id in tracker.signals
        metrics = tracker.signals[signal_id]
        assert metrics.strategy_name == "TestStrategy"
        assert metrics.confidence == 0.75

    def test_record_fill_tracks_slippage(self):
        """Should track slippage on fill"""
        tracker = SignalProfitabilityTracker()

        signal = Signal(
            timestamp=datetime.utcnow(),
            market_id="TEST-001",
            strategy_name="TestStrategy",
            direction=Direction.BUY,
            outcome=Outcome.YES,
            contracts=100,
            confidence=0.75,
            estimated_price=0.55,
        )

        signal_id = tracker.record_signal(signal)

        # Fill at worse price (slippage)
        tracker.record_fill(
            signal_id=signal_id,
            fill_price=0.56,
            fill_timestamp=datetime.utcnow(),
        )

        metrics = tracker.signals[signal_id]
        assert metrics.filled
        assert metrics.fill_price == 0.56
        assert metrics.fill_slippage == 0.01  # 0.56 - 0.55

    def test_record_settlement_calculates_pnl(self):
        """Should calculate P&L on settlement"""
        tracker = SignalProfitabilityTracker()

        signal = Signal(
            timestamp=datetime.utcnow(),
            market_id="TEST-001",
            strategy_name="TestStrategy",
            direction=Direction.BUY,
            outcome=Outcome.YES,
            contracts=100,
            confidence=0.75,
            estimated_price=0.55,
        )

        signal_id = tracker.record_signal(signal)
        tracker.record_fill(signal_id, 0.55, datetime.utcnow())

        # Signal was correct
        tracker.record_settlement(
            signal_id=signal_id,
            pnl=45.0,  # Won $1 per contract - cost
            winning_outcome=Outcome.YES,
            settlement_time=datetime.utcnow() + timedelta(days=7),
        )

        metrics = tracker.signals[signal_id]
        assert metrics.settled
        assert metrics.settlement_pnl == 45.0
        assert metrics.was_correct

    def test_strategy_stats_accuracy_calculation(self):
        """Should calculate strategy accuracy correctly"""
        tracker = SignalProfitabilityTracker()

        # Create 3 signals: 2 correct, 1 wrong
        for i in range(3):
            signal = Signal(
                timestamp=datetime.utcnow(),
                market_id=f"TEST-{i:03d}",
                strategy_name="TestStrategy",
                direction=Direction.BUY,
                outcome=Outcome.YES if i < 2 else Outcome.NO,
                contracts=100,
                confidence=0.75,
            )

            signal_id = tracker.record_signal(signal)
            tracker.record_fill(signal_id, 0.55, datetime.utcnow())

            # Settle all as YES
            tracker.record_settlement(
                signal_id=signal_id,
                pnl=45.0 if i < 2 else -55.0,
                winning_outcome=Outcome.YES,
                settlement_time=datetime.utcnow(),
            )

        stats = tracker.get_strategy_stats("TestStrategy")
        assert stats is not None
        assert stats.total_signals == 3
        assert stats.settled_signals == 3
        assert stats.winning_signals == 2
        assert stats.accuracy == pytest.approx(2.0 / 3.0, rel=0.01)

    def test_low_quality_signals_detection(self):
        """Should detect strategies with low accuracy"""
        tracker = SignalProfitabilityTracker()

        # Create 10 signals, only 4 correct (40% accuracy)
        for i in range(10):
            signal = Signal(
                timestamp=datetime.utcnow(),
                market_id=f"TEST-{i:03d}",
                strategy_name="BadStrategy",
                direction=Direction.BUY,
                outcome=Outcome.YES,
                contracts=100,
                confidence=0.75,
            )

            signal_id = tracker.record_signal(signal)
            tracker.record_fill(signal_id, 0.55, datetime.utcnow())

            # Only first 4 are correct
            is_correct = i < 4
            tracker.record_settlement(
                signal_id=signal_id,
                pnl=45.0 if is_correct else -55.0,
                winning_outcome=Outcome.YES if is_correct else Outcome.NO,
                settlement_time=datetime.utcnow(),
            )

        low_quality = tracker.get_low_quality_signals(accuracy_threshold=0.45, min_settled_signals=10)

        assert "BadStrategy" in low_quality
        assert low_quality["BadStrategy"].accuracy < 0.45

    def test_dashboard_summary(self):
        """Should provide comprehensive dashboard summary"""
        tracker = SignalProfitabilityTracker()

        # Create mixed signals
        for i in range(5):
            signal = Signal(
                timestamp=datetime.utcnow(),
                market_id=f"TEST-{i:03d}",
                strategy_name="TestStrategy" if i < 3 else "OtherStrategy",
                direction=Direction.BUY,
                outcome=Outcome.YES,
                contracts=100,
                confidence=0.75,
            )

            signal_id = tracker.record_signal(signal)
            tracker.record_fill(signal_id, 0.55, datetime.utcnow())
            tracker.record_settlement(
                signal_id=signal_id,
                pnl=45.0 if i % 2 == 0 else -55.0,
                winning_outcome=Outcome.YES if i % 2 == 0 else Outcome.NO,
                settlement_time=datetime.utcnow(),
            )

        summary = tracker.get_dashboard_summary()

        assert summary['total_signals'] == 5
        assert summary['settled_signals'] == 5
        assert 'strategy_stats' in summary
        assert 'low_quality_strategies' in summary

    def test_recent_signals_filtering(self):
        """Should filter signals by time window"""
        tracker = SignalProfitabilityTracker()

        # Create old and recent signals
        old_time = datetime.utcnow() - timedelta(hours=48)
        recent_time = datetime.utcnow()

        for i in range(3):
            signal = Signal(
                timestamp=old_time if i < 2 else recent_time,
                market_id=f"TEST-{i:03d}",
                strategy_name="TestStrategy",
                direction=Direction.BUY,
                outcome=Outcome.YES,
                contracts=100,
                confidence=0.75,
            )
            tracker.record_signal(signal)

        # Get signals from last 24 hours
        recent = tracker.get_recent_signals(lookback_hours=24)

        assert len(recent) == 1
        assert recent[0].timestamp >= datetime.utcnow() - timedelta(hours=24)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
