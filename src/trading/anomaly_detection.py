"""Anomaly detection and market condition filtering"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import deque
import math

from src.data.models import Signal, MarketState, Outcome
from src.data.news_models import SentimentScore

logger = logging.getLogger(__name__)


@dataclass
class AnomalyAlert:
    """Alert for detected market anomaly"""
    anomaly_type: str  # 'flash_crash', 'volume_drop', 'volatility_spike', 'liquidity_evaporation'
    severity: str  # 'low', 'medium', 'high', 'critical'
    market_id: str
    timestamp: datetime
    description: str
    recommended_action: str


class FlashCrashDetector:
    """Detects rapid price movements indicating flash crashes"""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.price_move_threshold_pct = self.config.get('price_move_threshold_pct', 5.0)
        self.lookback_seconds = self.config.get('lookback_seconds', 60)
        self.min_moves_to_trigger = self.config.get('min_moves_to_trigger', 2)

        self.price_history: Dict[str, deque] = {}  # market_id -> [(timestamp, price)]

    def check_for_flash_crash(
        self,
        market_id: str,
        market_state: MarketState,
    ) -> Optional[AnomalyAlert]:
        """Detect flash crash based on rapid price movement

        Args:
            market_id: Market ID
            market_state: Current market state

        Returns:
            AnomalyAlert if flash crash detected, else None
        """
        if market_id not in self.price_history:
            self.price_history[market_id] = deque(maxlen=1000)

        # Record current price
        current_price = market_state.yes_mid
        now = datetime.utcnow()
        self.price_history[market_id].append((now, current_price))

        # Check for large moves in recent history
        cutoff_time = now - timedelta(seconds=self.lookback_seconds)
        recent_prices = [
            (t, p) for t, p in self.price_history[market_id]
            if t >= cutoff_time
        ]

        if len(recent_prices) < 2:
            return None

        # Calculate price swings
        swings = []
        for i in range(1, len(recent_prices)):
            prev_price = recent_prices[i - 1][1]
            curr_price = recent_prices[i][1]
            if prev_price > 0:
                move_pct = abs(curr_price - prev_price) / prev_price * 100
                swings.append(move_pct)

        # Count large moves
        large_moves = sum(1 for s in swings if s > self.price_move_threshold_pct)

        if large_moves >= self.min_moves_to_trigger:
            alert = AnomalyAlert(
                anomaly_type='flash_crash',
                severity='critical',
                market_id=market_id,
                timestamp=now,
                description=f"Flash crash detected: {large_moves} moves >5% in 60s",
                recommended_action="REDUCE_POSITION_SIZE, INCREASE_LIMITS",
            )
            logger.warning(f"Flash crash alert: {alert.description}")
            return alert

        return None


class VolumeAnomalyDetector:
    """Detects unusual volume patterns"""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.volume_drop_threshold_pct = self.config.get('volume_drop_threshold_pct', 50.0)
        self.volume_spike_threshold_pct = self.config.get('volume_spike_threshold_pct', 200.0)
        self.lookback_periods = self.config.get('lookback_periods', 10)

        self.volume_history: Dict[str, deque] = {}  # market_id -> [volume]

    def check_for_volume_anomaly(
        self,
        market_id: str,
        market_state: MarketState,
    ) -> Optional[AnomalyAlert]:
        """Detect volume anomalies

        Args:
            market_id: Market ID
            market_state: Current market state

        Returns:
            AnomalyAlert if anomaly detected, else None
        """
        if market_id not in self.volume_history:
            self.volume_history[market_id] = deque(maxlen=100)

        current_volume = market_state.volume_24h or 1000

        # Record current volume
        self.volume_history[market_id].append(current_volume)

        if len(self.volume_history[market_id]) < self.lookback_periods:
            return None

        # Calculate average historical volume
        historical = list(self.volume_history[market_id])[:-1]  # Exclude current
        avg_volume = sum(historical) / len(historical)

        # Check for drop
        if avg_volume > 0 and current_volume < avg_volume * (1 - self.volume_drop_threshold_pct / 100):
            alert = AnomalyAlert(
                anomaly_type='volume_drop',
                severity='high',
                market_id=market_id,
                timestamp=datetime.utcnow(),
                description=f"Volume drop: {current_volume} vs avg {avg_volume:.0f}",
                recommended_action="SKIP_EXECUTION, MONITOR",
            )
            logger.warning(f"Volume anomaly: {alert.description}")
            return alert

        # Check for spike
        if current_volume > avg_volume * (1 + self.volume_spike_threshold_pct / 100):
            alert = AnomalyAlert(
                anomaly_type='volume_spike',
                severity='low',
                market_id=market_id,
                timestamp=datetime.utcnow(),
                description=f"Volume spike: {current_volume} vs avg {avg_volume:.0f}",
                recommended_action="INCREASE_POSITION_SIZE",  # Opportunity to execute larger orders
            )
            logger.info(f"Volume spike: {alert.description}")
            return alert

        return None


class VolatilityAnomalyDetector:
    """Detects unusual volatility"""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.volatility_spike_percentile = self.config.get('volatility_spike_percentile', 90)
        self.lookback_periods = self.config.get('lookback_periods', 30)

        self.volatility_history: Dict[str, deque] = {}  # market_id -> [volatility]

    def check_for_volatility_anomaly(
        self,
        market_id: str,
        market_state: MarketState,
        recent_volatility: Optional[float] = None,
    ) -> Optional[AnomalyAlert]:
        """Detect volatility spikes

        Args:
            market_id: Market ID
            market_state: Current market state
            recent_volatility: Recent realized volatility (if available)

        Returns:
            AnomalyAlert if anomaly detected, else None
        """
        if not recent_volatility:
            # Estimate volatility from spread
            spread = market_state.yes_ask - market_state.yes_bid
            mid = market_state.yes_mid
            recent_volatility = spread / mid if mid > 0 else 0.0

        if market_id not in self.volatility_history:
            self.volatility_history[market_id] = deque(maxlen=100)

        self.volatility_history[market_id].append(recent_volatility)

        if len(self.volatility_history[market_id]) < self.lookback_periods:
            return None

        # Calculate percentile
        sorted_vols = sorted(self.volatility_history[market_id])
        percentile_idx = int(len(sorted_vols) * self.volatility_spike_percentile / 100)
        percentile_vol = sorted_vols[percentile_idx]

        if recent_volatility > percentile_vol * 1.5:  # 50% above percentile
            alert = AnomalyAlert(
                anomaly_type='volatility_spike',
                severity='high',
                market_id=market_id,
                timestamp=datetime.utcnow(),
                description=f"Volatility spike: {recent_volatility:.1%} vs {percentile_vol:.1%}",
                recommended_action="REDUCE_POSITION_SIZE, WAIT_FOR_CALM",
            )
            logger.warning(f"Volatility anomaly: {alert.description}")
            return alert

        return None


class CalendarEventFilter:
    """Filters trading based on scheduled economic events"""

    # Hardcoded major event calendar
    MAJOR_EVENTS = {
        'FOMC': {
            'months': [1, 3, 5, 6, 7, 9, 11, 12],  # Federal Reserve meetings
            'volatility_multiplier': 5.0,
        },
        'CPI': {
            'months': list(range(1, 13)),  # Monthly
            'day_of_month': 12,  # Usually mid-month
            'volatility_multiplier': 3.0,
        },
        'JOBS': {
            'months': list(range(1, 13)),  # Monthly
            'day_of_month': 5,  # First Friday
            'volatility_multiplier': 3.0,
        },
        'ELECTION': {
            'months': [11],  # November
            'volatility_multiplier': 2.0,
        },
    }

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.lookback_hours = self.config.get('lookback_hours', 24)
        self.lookahead_hours = self.config.get('lookahead_hours', 48)

    def get_upcoming_events(self, now: datetime) -> List[Dict]:
        """Get upcoming major events

        Args:
            now: Current datetime

        Returns:
            List of upcoming events
        """
        upcoming = []
        lookahead = now + timedelta(hours=self.lookahead_hours)

        # Simplified: just check if we're in a major event month
        for event_name, event_config in self.MAJOR_EVENTS.items():
            if now.month in event_config['months']:
                upcoming.append({
                    'name': event_name,
                    'volatility_multiplier': event_config['volatility_multiplier'],
                    'hours_until': 24,  # Rough estimate
                })

        return upcoming

    def adjust_position_size_for_events(
        self,
        signal: Signal,
        base_size: int,
    ) -> int:
        """Adjust position size based on upcoming events

        Args:
            signal: Trading signal
            base_size: Base position size

        Returns:
            Adjusted position size
        """
        upcoming_events = self.get_upcoming_events(datetime.utcnow())

        if not upcoming_events:
            return base_size

        # Reduce position size for events
        reduction_factor = 1.0
        for event in upcoming_events:
            reduction_factor *= (1.0 / event['volatility_multiplier'])

        adjusted_size = int(base_size * reduction_factor)

        if adjusted_size < base_size:
            logger.info(
                f"Reduced position size from {base_size} to {adjusted_size} "
                f"due to upcoming events: {[e['name'] for e in upcoming_events]}"
            )

        return adjusted_size


class SentimentAnomalyFilter:
    """Filters signals based on news sentiment and anomalies"""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.sentiment_confidence_weight = self.config.get('sentiment_confidence_weight', 0.3)
        self.min_sentiment_magnitude = self.config.get('min_sentiment_magnitude', 0.3)

    def adjust_signal_confidence(
        self,
        signal: Signal,
        sentiment_score: Optional[SentimentScore] = None,
    ) -> float:
        """Adjust signal confidence based on news sentiment

        Args:
            signal: Trading signal
            sentiment_score: News sentiment (if available)

        Returns:
            Adjusted confidence multiplier
        """
        if not sentiment_score:
            return 1.0

        # Check if sentiment aligns with signal direction
        sentiment_aligned = False
        if signal.outcome == Outcome.YES and sentiment_score.sentiment > 0:
            sentiment_aligned = True
        elif signal.outcome == Outcome.NO and sentiment_score.sentiment < 0:
            sentiment_aligned = True

        if not sentiment_aligned:
            # Sentiment opposes signal
            adjustment = 1.0 - (abs(sentiment_score.sentiment) * self.sentiment_confidence_weight)
            adjustment = max(0.5, min(1.0, adjustment))  # Floor at 0.5x
            logger.info(
                f"Reduced signal confidence to {adjustment:.2f}x due to "
                f"opposing sentiment ({sentiment_score.sentiment:.2f})"
            )
            return adjustment
        else:
            # Sentiment supports signal - slight boost
            adjustment = 1.0 + (abs(sentiment_score.sentiment) * self.sentiment_confidence_weight * 0.25)
            adjustment = min(1.2, adjustment)  # Cap at 1.2x
            return adjustment

    def check_news_anomaly(self, sentiment_score: SentimentScore) -> Optional[str]:
        """Check if sentiment is anomalous

        Args:
            sentiment_score: News sentiment

        Returns:
            Anomaly description if detected, else None
        """
        # Extreme sentiment could indicate flash news or market shock
        if abs(sentiment_score.sentiment) > 0.9:
            return f"Extreme sentiment detected ({sentiment_score.sentiment:.2f})"

        # Low confidence on strong sentiment could be misleading
        if abs(sentiment_score.sentiment) > 0.7 and sentiment_score.confidence < 0.4:
            return "Low confidence on strong sentiment - possible false signal"

        return None


class AnomalyDetectionEngine:
    """Orchestrates all anomaly detection"""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.flash_crash_detector = FlashCrashDetector(self.config.get('flash_crash', {}))
        self.volume_detector = VolumeAnomalyDetector(self.config.get('volume', {}))
        self.volatility_detector = VolatilityAnomalyDetector(self.config.get('volatility', {}))
        self.calendar_filter = CalendarEventFilter(self.config.get('calendar', {}))
        self.sentiment_filter = SentimentAnomalyFilter(self.config.get('sentiment', {}))

        self.alerts: deque = deque(maxlen=1000)

    def check_market_conditions(
        self,
        market_id: str,
        market_state: MarketState,
    ) -> List[AnomalyAlert]:
        """Check for all market anomalies

        Args:
            market_id: Market ID
            market_state: Current market state

        Returns:
            List of anomaly alerts
        """
        alerts = []

        # Check for flash crashes
        flash_crash_alert = self.flash_crash_detector.check_for_flash_crash(market_id, market_state)
        if flash_crash_alert:
            alerts.append(flash_crash_alert)

        # Check for volume anomalies
        volume_alert = self.volume_detector.check_for_volume_anomaly(market_id, market_state)
        if volume_alert:
            alerts.append(volume_alert)

        # Check for volatility spikes
        volatility_alert = self.volatility_detector.check_for_volatility_anomaly(market_id, market_state)
        if volatility_alert:
            alerts.append(volatility_alert)

        # Store alerts
        for alert in alerts:
            self.alerts.append(alert)

        return alerts

    def should_trade_during_anomalies(self, alerts: List[AnomalyAlert]) -> bool:
        """Determine if trading should proceed given detected anomalies

        Args:
            alerts: List of anomaly alerts

        Returns:
            True if safe to trade, False if should skip
        """
        critical_anomalies = [a for a in alerts if a.severity == 'critical']
        if critical_anomalies:
            logger.warning(f"Skipping trade due to critical anomalies: {critical_anomalies}")
            return False

        return True

    def get_recent_alerts(self, hours: int = 1) -> List[AnomalyAlert]:
        """Get recent anomaly alerts

        Args:
            hours: Hours to look back

        Returns:
            List of recent alerts
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return [a for a in self.alerts if a.timestamp >= cutoff]
