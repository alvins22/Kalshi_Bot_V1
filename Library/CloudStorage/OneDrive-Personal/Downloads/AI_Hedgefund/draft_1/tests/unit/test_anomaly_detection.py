"""Tests for anomaly detection system"""

import pytest
from datetime import datetime, timedelta

from src.trading.anomaly_detection import (
    FlashCrashDetector,
    VolumeAnomalyDetector,
    VolatilityAnomalyDetector,
    CalendarEventFilter,
    AnomalyDetectionEngine,
)
from src.data.models import MarketState, Outcome


class MockMarketState:
    """Mock market state for testing"""

    def __init__(
        self,
        yes_bid=0.45,
        yes_ask=0.55,
        no_bid=0.45,
        no_ask=0.55,
        volume_24h=1000,
    ):
        self.yes_bid = yes_bid
        self.yes_ask = yes_ask
        self.no_bid = no_bid
        self.no_ask = no_ask
        self.volume_24h = volume_24h
        self.timestamp = datetime.utcnow()
        self.market_id = "TEST-001"

    @property
    def yes_mid(self):
        return (self.yes_bid + self.yes_ask) / 2

    @property
    def no_mid(self):
        return (self.no_bid + self.no_ask) / 2


class TestFlashCrashDetector:
    """Test flash crash detection"""

    def test_detects_rapid_price_moves(self):
        """Should detect rapid price movements"""
        detector = FlashCrashDetector({
            'price_move_threshold_pct': 5.0,
            'lookback_seconds': 60,
            'min_moves_to_trigger': 2,
        })

        # Normal price
        state1 = MockMarketState(yes_mid=0.50)
        detector.check_for_flash_crash("TEST-001", state1)

        # Large move (5%)
        state2 = MockMarketState(yes_mid=0.525)
        detector.check_for_flash_crash("TEST-001", state2)

        # Another large move
        state3 = MockMarketState(yes_mid=0.550)
        alert = detector.check_for_flash_crash("TEST-001", state3)

        # Should detect after 2+ moves
        assert alert is not None
        assert alert.anomaly_type == 'flash_crash'
        assert alert.severity == 'critical'

    def test_ignores_normal_movements(self):
        """Should not alert on normal price moves"""
        detector = FlashCrashDetector({
            'price_move_threshold_pct': 5.0,
            'lookback_seconds': 60,
        })

        # Make small moves
        for i in range(10):
            state = MockMarketState(yes_mid=0.50 + i * 0.001)  # 0.1% moves
            alert = detector.check_for_flash_crash("TEST-001", state)
            assert alert is None


class TestVolumeAnomalyDetector:
    """Test volume anomaly detection"""

    def test_detects_volume_drops(self):
        """Should detect abnormal volume drops"""
        detector = VolumeAnomalyDetector({
            'volume_drop_threshold_pct': 50.0,
            'lookback_periods': 3,
        })

        # Build history
        for i in range(4):
            state = MockMarketState(volume_24h=1000)
            detector.check_for_volume_anomaly("TEST-001", state)

        # Sharp drop
        state_drop = MockMarketState(volume_24h=400)
        alert = detector.check_for_volume_anomaly("TEST-001", state_drop)

        assert alert is not None
        assert alert.anomaly_type == 'volume_drop'

    def test_detects_volume_spikes(self):
        """Should detect volume spikes (opportunities)"""
        detector = VolumeAnomalyDetector({
            'volume_spike_threshold_pct': 200.0,
            'lookback_periods': 3,
        })

        # Build history
        for i in range(4):
            state = MockMarketState(volume_24h=1000)
            detector.check_for_volume_anomaly("TEST-001", state)

        # Volume spike
        state_spike = MockMarketState(volume_24h=3500)
        alert = detector.check_for_volume_anomaly("TEST-001", state_spike)

        assert alert is not None
        assert alert.anomaly_type == 'volume_spike'
        assert alert.severity == 'low'


class TestVolatilityAnomalyDetector:
    """Test volatility anomaly detection"""

    def test_detects_volatility_spikes(self):
        """Should detect elevated volatility"""
        detector = VolatilityAnomalyDetector({
            'volatility_spike_percentile': 80,
            'lookback_periods': 10,
        })

        # Build normal history
        for i in range(10):
            normal_volatility = 0.02  # 2%
            detector.check_for_volatility_anomaly("TEST-001", MockMarketState(), normal_volatility)

        # Spike
        spike_volatility = 0.10  # 10%
        alert = detector.check_for_volatility_anomaly("TEST-001", MockMarketState(), spike_volatility)

        assert alert is not None
        assert alert.anomaly_type == 'volatility_spike'


class TestCalendarEventFilter:
    """Test calendar event filtering"""

    def test_adjusts_position_size_for_events(self):
        """Should reduce position size during major events"""
        filter = CalendarEventFilter()

        # In FOMC month (January)
        signal_jan = type('Signal', (), {
            'outcome': Outcome.YES,
            'market_id': 'TEST-001',
        })()

        base_size = 1000

        # During event month, size should be reduced
        adjusted = filter.adjust_position_size_for_events(signal_jan, base_size)

        # Should be reduced due to FOMC event
        assert adjusted <= base_size

    def test_preserves_size_outside_events(self):
        """Should preserve position size outside of event windows"""
        import time
        from unittest.mock import patch

        filter = CalendarEventFilter()

        signal = type('Signal', (), {
            'outcome': Outcome.YES,
            'market_id': 'TEST-001',
        })()

        base_size = 1000

        # Mock to a month with fewer events
        with patch('src.trading.anomaly_detection.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2026, 2, 15)  # February (few events)
            adjusted = filter.adjust_position_size_for_events(signal, base_size)

            # Should keep size roughly the same
            assert adjusted >= base_size * 0.8  # Some tolerance


class TestAnomalyDetectionEngine:
    """Test integrated anomaly detection"""

    def test_checks_multiple_anomalies(self):
        """Should check all anomaly types"""
        engine = AnomalyDetectionEngine()

        # Create normal market state
        state = MockMarketState()

        # Should complete without errors
        alerts = engine.check_market_conditions("TEST-001", state)

        assert isinstance(alerts, list)

    def test_returns_empty_on_normal_conditions(self):
        """Should return no alerts on normal market conditions"""
        engine = AnomalyDetectionEngine()

        state = MockMarketState()

        # Multiple checks on stable market
        alerts1 = engine.check_market_conditions("TEST-001", state)
        alerts2 = engine.check_market_conditions("TEST-001", state)
        alerts3 = engine.check_market_conditions("TEST-001", state)

        # Should have no critical alerts
        all_alerts = alerts1 + alerts2 + alerts3
        critical = [a for a in all_alerts if a.severity == 'critical']
        assert len(critical) == 0

    def test_trading_blocked_on_critical_anomaly(self):
        """Should block trading when critical anomalies detected"""
        engine = AnomalyDetectionEngine()

        # Simulate critical alert
        from src.trading.anomaly_detection import AnomalyAlert

        critical_alert = AnomalyAlert(
            anomaly_type='flash_crash',
            severity='critical',
            market_id='TEST-001',
            timestamp=datetime.utcnow(),
            description="Critical anomaly",
            recommended_action="BLOCK_TRADING",
        )

        # Should block trading
        assert not engine.should_trade_during_anomalies([critical_alert])

    def test_trading_allowed_on_low_severity(self):
        """Should allow trading on low severity anomalies"""
        engine = AnomalyDetectionEngine()

        from src.trading.anomaly_detection import AnomalyAlert

        low_alert = AnomalyAlert(
            anomaly_type='volume_spike',
            severity='low',
            market_id='TEST-001',
            timestamp=datetime.utcnow(),
            description="Volume spike (opportunity)",
            recommended_action="INCREASE_SIZE",
        )

        # Should allow trading
        assert engine.should_trade_during_anomalies([low_alert])


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
